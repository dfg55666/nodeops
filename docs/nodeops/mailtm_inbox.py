"""
mail.tm inbox helper (stdlib-only).

This module is intentionally self-contained so it can be copied into other scripts/projects.

Example:

    from auth.mailtm_inbox import MailTMInbox

    inbox = MailTMInbox(logger=print)
    email = inbox.generate_email()
    print("email:", email)
    code = inbox.wait_for_verification_code(timeout_s=180, debug=True)
    print("code:", code)
"""

from __future__ import annotations

import html as _html
import imaplib
import json
import random
import re
import time
import urllib.error
import urllib.request
from email import message_from_bytes
from email.header import decode_header
from email.message import Message
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, List, Optional, Tuple


_DEFAULT_TIMEOUT_S = 30
_API_BASE = "https://api.mail.tm"
_DEFAULT_MAILTM_PASSWORD = "@#Dfg55666"
_HUMAN_NAME_PREFIXES = (
    "liam",
    "noah",
    "oliver",
    "emma",
    "sophia",
    "ava",
    "mia",
    "lucas",
    "jack",
    "ryan",
    "zoe",
    "nora",
    "chris",
    "alex",
    "ella",
    "ivy",
    "leo",
    "luna",
    "mason",
    "ethan",
)


_CODE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"Your verification code is[:\s]+(\d{6})",
        r"verification code[:\s]+(?:is[:\s]+)?(\d{6})",
        r"verify(?:ing)? code[:\s]+(?:is[:\s]+)?(\d{6})",
        r"otp[:\s]+(\d{6})",
        r"code[:\s]+(\d{6})",
        r"<strong>(\d{6})</strong>",
        r"<span[^>]*>(\d{6})</span>",
        r"\b(\d{6})\b",
    ]
]


def _generate_random_string(length: int) -> str:
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(random.choice(chars) for _ in range(length))


def _generate_human_like_username() -> str:
    prefix = random.choice(_HUMAN_NAME_PREFIXES)
    suffix = random.randint(10000, 99999)
    return f"{prefix}{suffix}"


def extract_verification_code(content: str) -> str:
    """
    Extract a 6-digit code from text or HTML.

    It tries patterns first, then various fallbacks to support segmented HTML digits.
    """

    if not content:
        return ""

    candidates = [content]

    # Strip HTML tags to make codes like "<span>1</span>...<span>6</span>" parseable.
    try:
        stripped = re.sub(r"<[^>]+>", " ", content)
        stripped = _html.unescape(stripped)
        if stripped and stripped != content:
            candidates.append(stripped)
    except Exception:
        pass

    for candidate in candidates:
        for regex in _CODE_PATTERNS:
            match = regex.search(candidate)
            if match:
                return match.group(1)

    # Keyword-window fallback: reduce false positives from footers/dates.
    keyword_match = re.search(r"(verification|verify|otp|code)", content, flags=re.IGNORECASE)
    if keyword_match:
        window = content[keyword_match.end() : keyword_match.end() + 3000]
        digits = re.sub(r"\D", "", window)
        match = re.search(r"\d{6}", digits)
        if match:
            return match.group(0)

    # Generic fallback: 6 digits with arbitrary separators (including HTML tags).
    spaced = re.search(
        r"(\d)\D{0,200}(\d)\D{0,200}(\d)\D{0,200}(\d)\D{0,200}(\d)\D{0,200}(\d)",
        content,
    )
    if spaced:
        return "".join(spaced.groups())

    # Last resort: take the first 6-digit run from all digits.
    digits = re.sub(r"\D", "", content)
    match = re.search(r"\d{6}", digits)
    if match:
        return match.group(0)

    return ""


class MailTMInbox:
    """
    Minimal mail.tm wrapper to:
    - create a disposable inbox (account)
    - poll for messages
    - extract a 6-digit verification code
    """

    def __init__(
        self,
        password: Optional[str] = None,
        logger: Optional[Callable[[str], None]] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        self.password = password or _DEFAULT_MAILTM_PASSWORD
        self.email = ""
        self.token = ""
        self._logger = logger
        self._user_agent = user_agent or "mailtm-inbox/1.0"

    def _log(self, msg: str) -> None:
        if self._logger is None:
            return
        try:
            self._logger(msg)
        except Exception:
            pass

    def _request_json(
        self,
        method: str,
        url: str,
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
    ) -> Tuple[int, Any, str]:
        payload = None
        req_headers: Dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": self._user_agent,
        }
        if headers:
            req_headers.update(headers)
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")

        request = urllib.request.Request(url, data=payload, method=method, headers=req_headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                status = response.getcode()
                text = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            status = error.code
            text = error.read().decode("utf-8", errors="replace")

        try:
            parsed = json.loads(text) if text else {}
        except json.JSONDecodeError:
            parsed = text

        return status, parsed, text

    def _login(self) -> None:
        if not self.email:
            raise RuntimeError("mail.tm login: email missing")

        status, payload, raw = self._request_json(
            "POST",
            f"{_API_BASE}/token",
            body={"address": self.email, "password": self.password},
        )
        if status != 200 or not isinstance(payload, dict) or not payload.get("token"):
            raise RuntimeError(f"mail.tm login failed ({status}): {raw}")
        self.token = str(payload.get("token"))

    def _list_domains(self) -> List[str]:
        status, payload, raw = self._request_json("GET", f"{_API_BASE}/domains")
        if status == 429:
            raise RuntimeError("mail.tm rate limited (429)")
        if status != 200:
            raise RuntimeError(f"mail.tm domains failed ({status}): {raw}")

        members: List[Dict[str, Any]] = []
        if isinstance(payload, list):
            members = [item for item in payload if isinstance(item, dict)]
        elif isinstance(payload, dict):
            value = payload.get("hydra:member")
            if isinstance(value, list):
                members = [item for item in value if isinstance(item, dict)]
            elif isinstance(payload.get("domains"), list):
                members = [item for item in payload.get("domains", []) if isinstance(item, dict)]

        domains: List[str] = []
        for item in members:
            domain = str(item.get("domain", "")).strip()
            if domain:
                domains.append(domain)

        if not domains:
            raw_preview = str(raw)[:240].replace("\n", " ")
            raise RuntimeError(f"mail.tm has no domain, payload={raw_preview}")

        return domains

    def _create_inbox_once(self) -> str:
        domains = self._list_domains()
        domain = str(domains[0]).strip()
        if not domain:
            raise RuntimeError("mail.tm domain missing")

        username = _generate_human_like_username()
        email = f"{username}@{domain}"
        status, _, raw = self._request_json(
            "POST",
            f"{_API_BASE}/accounts",
            body={"address": email, "password": self.password},
        )
        if status == 429:
            raise RuntimeError("mail.tm rate limited (429)")
        if status != 201:
            raise RuntimeError(f"mail.tm create account failed ({status}): {raw}")

        self.email = email
        self._login()
        return email

    def generate_email(self, max_retries: int = 5) -> str:
        for retry in range(max_retries):
            if retry > 0:
                wait_s = 3 + retry * 3
                self._log(f"mail.tm retry #{retry}, wait {wait_s}s")
                time.sleep(wait_s)
            try:
                return self._create_inbox_once()
            except Exception as exc:
                # Best-effort retry behavior: back off on rate limiting.
                if "429" in str(exc) and retry + 1 < max_retries:
                    continue
                raise
        raise RuntimeError("mail.tm retries exhausted")

    def wait_for_verification_code(self, timeout_s: float, debug: bool = False) -> str:
        if not self.token:
            raise RuntimeError("mail.tm token missing")

        deadline = time.monotonic() + float(timeout_s)
        seen_ids: set[str] = set()
        last_preview = ""

        while time.monotonic() < deadline:
            status, payload, _ = self._request_json(
                "GET",
                f"{_API_BASE}/messages",
                headers={"Authorization": f"Bearer {self.token}"},
            )
            if status != 200:
                time.sleep(3)
                continue

            members: List[Dict[str, Any]] = []
            if isinstance(payload, list):
                members = [item for item in payload if isinstance(item, dict)]
            elif isinstance(payload, dict):
                value = payload.get("hydra:member")
                if isinstance(value, list):
                    members = [item for item in value if isinstance(item, dict)]
                elif isinstance(payload.get("messages"), list):
                    members = [item for item in payload.get("messages", []) if isinstance(item, dict)]

            if debug:
                subjects = []
                for msg in members[:5]:
                    subj = str(msg.get("subject") or "")
                    if subj:
                        subjects.append(subj[:80])
                self._log(f"mail.tm inbox poll: messages={len(members)}, subjects={subjects}")

            for msg in members:
                msg_id = str(msg.get("id", "")).strip()
                if not msg_id or msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)

                status, detail, _ = self._request_json(
                    "GET",
                    f"{_API_BASE}/messages/{msg_id}",
                    headers={"Authorization": f"Bearer {self.token}"},
                )
                if status != 200 or not isinstance(detail, dict):
                    continue

                subject = str(detail.get("subject") or "")
                text = str(detail.get("text") or "")
                html_list = detail.get("html")

                chunks: List[str] = [subject, text]
                if isinstance(html_list, list):
                    chunks.extend(str(html) for html in html_list)

                combined = "\n".join(chunks)
                code = extract_verification_code(combined)
                if code:
                    return code

                if debug:
                    preview = re.sub(r"\s+", " ", combined).strip()
                    last_preview = preview[:360]
                    self._log(f"mail.tm message {msg_id} parsed no code; preview={last_preview!r}")

            time.sleep(3)

        suffix = f"; last_preview={last_preview!r}" if last_preview else ""
        raise RuntimeError("mail.tm wait for verification code timeout" + suffix)


def _decode_header_to_text(raw: str) -> str:
    if not raw:
        return ""
    parts: List[str] = []
    for value, encoding in decode_header(raw):
        if isinstance(value, bytes):
            enc = encoding or "utf-8"
            try:
                parts.append(value.decode(enc, errors="replace"))
            except Exception:
                parts.append(value.decode("utf-8", errors="replace"))
        else:
            parts.append(str(value))
    return "".join(parts)


def _message_date_epoch(msg: Message) -> float:
    raw = msg.get("Date", "")
    if not raw:
        return 0.0
    try:
        dt = parsedate_to_datetime(raw)
    except Exception:
        return 0.0
    try:
        return dt.timestamp()
    except Exception:
        return 0.0


def _extract_message_text(msg: Message) -> str:
    chunks: List[str] = []
    subject = _decode_header_to_text(msg.get("Subject", ""))
    if subject:
        chunks.append(subject)

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type().lower()
            disp = str(part.get("Content-Disposition", "")).lower()
            if "attachment" in disp:
                continue
            if ctype not in ("text/plain", "text/html"):
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except Exception:
                text = payload.decode("utf-8", errors="replace")
            chunks.append(text)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                text = payload.decode(charset, errors="replace")
            except Exception:
                text = payload.decode("utf-8", errors="replace")
            chunks.append(text)

    return "\n".join(chunks)


class QQIMAPInbox:
    """
    QQ IMAP mailbox helper:
    - generate human-like alias email with a fixed domain
    - poll IMAP folder and extract a 6-digit verification code
    """

    def __init__(
        self,
        qq_email: str,
        qq_password: str,
        qq_imap_server: str = "imap.qq.com",
        qq_imap_port: int = 993,
        folder: str = "INBOX",
        alias_domain: str = "jdjf999.ggff.net",
        logger: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.qq_email = qq_email.strip()
        self.qq_password = qq_password.strip()
        self.qq_imap_server = qq_imap_server.strip() or "imap.qq.com"
        self.qq_imap_port = int(qq_imap_port)
        self.folder = folder.strip() or "INBOX"
        self.alias_domain = alias_domain.strip() or "jdjf999.ggff.net"
        self.email = ""
        self._logger = logger
        self._created_at_epoch = time.time()

    def _log(self, msg: str) -> None:
        if self._logger is None:
            return
        try:
            self._logger(msg)
        except Exception:
            pass

    def generate_email(self, prefix_len: int = 10) -> str:
        # Keep the method signature for compatibility; aliases now use
        # human-name + digits format (e.g. mia48291@domain).
        _ = prefix_len
        prefix = _generate_human_like_username()
        self.email = f"{prefix}@{self.alias_domain}"
        self._created_at_epoch = time.time()
        return self.email

    def reset_start_time(self) -> None:
        self._created_at_epoch = time.time()

    def _connect_and_select(self, readonly: bool = True) -> imaplib.IMAP4_SSL:
        conn = imaplib.IMAP4_SSL(self.qq_imap_server, self.qq_imap_port)
        login_status, _ = conn.login(self.qq_email, self.qq_password)
        if login_status != "OK":
            raise RuntimeError(f"qq imap login failed: {login_status}")
        select_status, _ = conn.select(self.folder, readonly=readonly)
        if select_status != "OK":
            raise RuntimeError(f"qq imap select folder failed: {self.folder}")
        return conn

    def _recipient_match(self, msg: Message, recipient: str) -> bool:
        if not recipient:
            return True
        recipient_l = recipient.lower()
        headers = [
            msg.get("To", ""),
            msg.get("Delivered-To", ""),
            msg.get("X-Original-To", ""),
            msg.get("Cc", ""),
        ]
        joined = " ".join(_decode_header_to_text(h).lower() for h in headers if h)
        return recipient_l in joined

    def _extract_recipients(self, msg: Message) -> List[str]:
        headers = [
            msg.get("To", ""),
            msg.get("Delivered-To", ""),
            msg.get("X-Original-To", ""),
            msg.get("Cc", ""),
        ]
        joined = " ".join(_decode_header_to_text(h).lower() for h in headers if h)
        return re.findall(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", joined)

    def wait_for_verification_codes(
        self,
        recipients: List[str],
        timeout_s: float,
        debug: bool = False,
        poll_interval_s: float = 4.0,
        max_scan_per_poll: int = 60,
        delete_on_match: bool = False,
    ) -> Dict[str, str]:
        normalized = [r.strip().lower() for r in recipients if str(r).strip()]
        unresolved = set(normalized)
        found: Dict[str, str] = {}
        if not unresolved:
            return found

        deadline = time.monotonic() + float(timeout_s)
        seen_uids: set[str] = set()
        last_preview = ""
        deleted_uids: List[str] = []

        conn: Optional[imaplib.IMAP4_SSL] = None
        try:
            while time.monotonic() < deadline and unresolved:
                if conn is None:
                    conn = self._connect_and_select(readonly=not delete_on_match)

                try:
                    status, data = conn.uid("search", None, "ALL")
                except (imaplib.IMAP4.abort, imaplib.IMAP4.error):
                    try:
                        conn.logout()
                    except Exception:
                        pass
                    conn = None
                    time.sleep(poll_interval_s)
                    continue

                if status != "OK" or not data or not data[0]:
                    if debug:
                        self._log(f"qq imap poll: no messages, unresolved={len(unresolved)}")
                    time.sleep(poll_interval_s)
                    continue

                all_uids = [u for u in data[0].decode(errors="ignore").split() if u]
                candidate_uids = list(reversed(all_uids[-max_scan_per_poll:]))

                if debug:
                    self._log(
                        f"qq imap poll: total={len(all_uids)}, scan={len(candidate_uids)}, unresolved={len(unresolved)}"
                    )

                for uid in candidate_uids:
                    if uid in seen_uids:
                        continue
                    seen_uids.add(uid)

                    fetch_status, fetch_data = conn.uid("fetch", uid, "(RFC822)")
                    if fetch_status != "OK" or not fetch_data:
                        continue

                    raw_bytes = b""
                    for part in fetch_data:
                        if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], (bytes, bytearray)):
                            raw_bytes = bytes(part[1])
                            break
                    if not raw_bytes:
                        continue

                    msg = message_from_bytes(raw_bytes)

                    msg_ts = _message_date_epoch(msg)
                    if msg_ts > 0 and msg_ts < self._created_at_epoch - 60:
                        continue

                    msg_recipients = set(self._extract_recipients(msg))
                    target_recipients = [r for r in unresolved if r in msg_recipients]
                    if not target_recipients:
                        continue

                    combined = _extract_message_text(msg)
                    code = extract_verification_code(combined)
                    if not code:
                        if debug:
                            preview = re.sub(r"\s+", " ", combined).strip()
                            last_preview = preview[:360]
                            self._log(f"qq imap uid={uid} no code; preview={last_preview!r}")
                        continue

                    for recipient in target_recipients:
                        found[recipient] = code
                        unresolved.discard(recipient)

                    if debug:
                        self._log(
                            f"qq imap uid={uid} matched={target_recipients} code={code} unresolved={len(unresolved)}"
                        )

                    if delete_on_match:
                        try:
                            store_status, _ = conn.uid("store", uid, "+FLAGS", "(\\Deleted)")
                            if store_status == "OK":
                                deleted_uids.append(uid)
                                if debug:
                                    self._log(f"qq imap uid={uid} marked deleted")
                        except Exception as exc:
                            if debug:
                                self._log(f"qq imap uid={uid} delete failed: {exc}")

                    if not unresolved:
                        break

                if unresolved:
                    time.sleep(poll_interval_s)

            if unresolved and debug:
                suffix = f"; last_preview={last_preview!r}" if last_preview else ""
                self._log(f"qq imap timeout unresolved={sorted(unresolved)}{suffix}")

            if delete_on_match and deleted_uids:
                try:
                    conn.expunge()
                    if debug:
                        self._log(f"qq imap expunged deleted messages count={len(deleted_uids)}")
                except Exception as exc:
                    if debug:
                        self._log(f"qq imap expunge failed: {exc}")

            return found
        finally:
            if conn is not None:
                try:
                    conn.logout()
                except Exception:
                    pass

    def wait_for_verification_code(
        self,
        timeout_s: float,
        debug: bool = False,
        recipient: Optional[str] = None,
        poll_interval_s: float = 4.0,
        max_scan_per_poll: int = 20,
        delete_on_match: bool = False,
    ) -> str:
        target = (recipient or self.email).strip().lower()
        if not target:
            raise RuntimeError("qq imap recipient missing")
        found = self.wait_for_verification_codes(
            recipients=[target],
            timeout_s=timeout_s,
            debug=debug,
            poll_interval_s=poll_interval_s,
            max_scan_per_poll=max_scan_per_poll,
            delete_on_match=delete_on_match,
        )
        if target in found:
            return found[target]
        raise RuntimeError("qq imap wait for verification code timeout")
