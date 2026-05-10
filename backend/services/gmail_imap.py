"""
Gmail IMAP verification code fetcher.

Mirrors the logic in browser-extension/nodeops-helper/scripts/fetch_verification_code.py
but as a reusable Python module (no subprocess needed).

Usage:
    from backend.services.gmail_imap import GmailIMAPInbox
    inbox = GmailIMAPInbox(email="feijidfg55@gmail.com", app_password="xxxx xxxx xxxx xxxx")
    code = await inbox.fetch_latest_code(to_email_contains="...", delete_best=True)
"""
from __future__ import annotations

import asyncio
import email as email_lib
import html
import imaplib
import logging
import re
import socket
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime
from typing import Optional

logger = logging.getLogger(__name__)

KEYWORDS = (
    "nodeops",
    "createos",
    "verification",
    "verify",
    "one-time",
    "otp",
    "code",
    "login",
    "signin",
    "sign in",
    "验证码",
)
OTP_PRIMARY_SENDER = "otp@reachout.nodeops.network"
OTP_SENDER_DOMAIN = "reachout.nodeops.network"
ALIAS_RECENT_SCAN_LIMIT = 8


def _decode_mime(value: str) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _extract_text(msg: Message) -> str:
    chunks = []
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct not in ("text/plain", "text/html"):
                continue
            raw = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            try:
                text = raw.decode(charset, errors="ignore")
            except Exception:
                text = raw.decode("utf-8", errors="ignore")
            if ct == "text/html":
                text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
                text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
                text = re.sub(r"<[^>]+>", " ", text)
                text = html.unescape(text)
            chunks.append(text)
    else:
        raw = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        try:
            chunks.append(raw.decode(charset, errors="ignore"))
        except Exception:
            chunks.append(raw.decode("utf-8", errors="ignore"))
    return "\n".join(chunks)


def _score_message(subject: str, sender: str, body: str) -> int:
    text = f"{subject}\n{sender}\n{body}".lower()
    score = 0
    for kw in KEYWORDS:
        if kw in text:
            score += 1
    if re.search(r"\b\d{4,8}\b", text):
        score += 2
    return score


def _find_codes(text: str) -> list[str]:
    seen: set[str] = set()
    codes: list[str] = []
    for code in re.findall(r"\b(\d{4,8})\b", text):
        if code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def _message_time(msg) -> datetime:
    dt_raw = msg.get("Date", "")
    try:
        dt = parsedate_to_datetime(dt_raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


def _apply_proxy(proxy_type: str, proxy_host: str, proxy_port: int):
    """Monkey-patch socket via PySocks. Returns original socket class or None."""
    try:
        import socks
    except ImportError:
        raise RuntimeError("PySocks not installed; install it with: pip install PySocks")

    proxy_map = {
        "socks5": socks.SOCKS5,
        "socks4": socks.SOCKS4,
        "http": socks.HTTP,
    }
    ptype = proxy_map.get(proxy_type.lower())
    if ptype is None:
        raise RuntimeError(f"Unsupported proxy type: {proxy_type}")

    original = socket.socket
    socks.set_default_proxy(ptype, proxy_host, proxy_port, rdns=True)
    socket.socket = socks.socksocket
    return original


class GmailIMAPFetchResult:
    def __init__(
        self,
        ok: bool,
        best_code: str = "",
        codes: list[str] | None = None,
        subject: str = "",
        sender: str = "",
        to: str = "",
        date: str = "",
        deleted: bool = False,
        error: str = "",
    ):
        self.ok = ok
        self.best_code = best_code
        self.codes = codes or []
        self.subject = subject
        self.sender = sender
        self.to = to
        self.date = date
        self.deleted = deleted
        self.error = error

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "best_code": self.best_code,
            "codes": self.codes,
            "subject": self.subject,
            "from": self.sender,
            "to": self.to,
            "date": self.date,
            "deleted": self.deleted,
            "error": self.error,
        }


class GmailIMAPInbox:
    """
    Synchronous IMAP fetcher for Gmail app-password auth.
    Wraps into async via run_in_executor for FastAPI compatibility.
    """

    DEFAULT_HOSTS = ["imap.gmail.com", "imap.googlemail.com"]

    def __init__(
        self,
        email_addr: str,
        app_password: str,
        imap_host: str = "imap.gmail.com",
        imap_port: int = 993,
        proxy_type: str = "http",
        proxy_host: str = "",
        proxy_port: int = 0,
        lookback_hours: int = 72,
        max_mails: int = 120,
    ):
        self.email_addr = email_addr.strip()
        # Strip spaces from app password (Google format: "xxxx xxxx xxxx xxxx")
        self.app_password = app_password.replace(" ", "").strip()
        self.imap_host = imap_host.strip() or "imap.gmail.com"
        self.imap_port = imap_port
        self.proxy_type = proxy_type or "http"
        self.proxy_host = proxy_host.strip()
        self.proxy_port = proxy_port
        self.lookback_hours = lookback_hours
        self.max_mails = max_mails

    def _get_hosts(self) -> list[str]:
        hosts = [self.imap_host]
        if self.imap_host.lower() == "imap.gmail.com":
            hosts.append("imap.googlemail.com")
        return hosts

    def _connect(self) -> imaplib.IMAP4_SSL:
        """Connect and login; tries both gmail hosts."""
        original_socket = None
        use_proxy = bool(self.proxy_host and self.proxy_port)
        if use_proxy:
            try:
                original_socket = _apply_proxy(self.proxy_type, self.proxy_host, int(self.proxy_port))
            except Exception as exc:
                raise RuntimeError(f"Proxy setup failed: {exc}") from exc

        last_exc: Exception | None = None
        imap: imaplib.IMAP4_SSL | None = None
        try:
            for host in self._get_hosts():
                try:
                    imap = imaplib.IMAP4_SSL(host, self.imap_port)
                    imap.login(self.email_addr, self.app_password)
                    imap.select("INBOX")
                    return imap
                except Exception as exc:
                    last_exc = exc
                    imap = None
        finally:
            if original_socket is not None:
                socket.socket = original_socket

        raise RuntimeError(f"IMAP connection/login failed: {last_exc}") from last_exc

    def _imap_search_ids(self, imap: imaplib.IMAP4_SSL, *criteria: str) -> list[bytes]:
        """Run IMAP SEARCH and return matched IDs (empty on failure)."""
        try:
            typ, data = imap.search(None, *criteria)
        except Exception as exc:
            logger.debug("IMAP search failed criteria=%s err=%s", criteria, exc)
            return []
        if typ != "OK" or not data or not data[0]:
            return []
        try:
            return list(data[0].split())
        except Exception:
            return []

    def _collect_candidate_ids(
        self,
        imap: imaplib.IMAP4_SSL,
        cutoff: datetime,
        to_email_contains: str,
    ) -> list[bytes]:
        """
        Collect message IDs with server-side IMAP search first.
        Prioritizes NodeOps OTP sender to avoid scanning unrelated emails.
        """
        since_token = cutoff.strftime("%d-%b-%Y")
        to_filter = str(to_email_contains or "").strip()

        search_plans: list[tuple[str, ...]] = []
        if to_filter:
            search_plans.append(("FROM", f"\"{OTP_PRIMARY_SENDER}\"", "TO", f"\"{to_filter}\"", "SINCE", since_token))
            search_plans.append(("TO", f"\"{to_filter}\"", "SINCE", since_token))
        else:
            search_plans.append(("FROM", f"\"{OTP_PRIMARY_SENDER}\"", "SINCE", since_token))
            search_plans.append(("FROM", f"\"{OTP_SENDER_DOMAIN}\"", "SINCE", since_token))

        collected: list[bytes] = []
        seen: set[bytes] = set()
        for criteria in search_plans:
            ids = self._imap_search_ids(imap, *criteria)
            for msg_id in ids:
                if msg_id in seen:
                    continue
                seen.add(msg_id)
                collected.append(msg_id)
            # Sender+alias exact hit is enough; stop early to reduce latency.
            if collected and criteria[:2] == ("FROM", f"\"{OTP_PRIMARY_SENDER}\"") and "TO" in criteria:
                break

        if to_filter and collected:
            # Alias workflow only needs the latest few matches for this exact
            # recipient; avoid scanning deep history.
            collected = collected[-ALIAS_RECENT_SCAN_LIMIT:]

        # Compatibility fallback (no alias filter only): if strict sender
        # searches return nothing, sample only recent messages.
        if not collected and not to_filter:
            recent_ids = self._imap_search_ids(imap, "SINCE", since_token)
            if recent_ids:
                collected = recent_ids[-max(10, min(self.max_mails, 30)):]

        return collected

    def fetch_latest_code_sync(
        self,
        to_email_contains: str = "",
        delete_best: bool = True,
    ) -> GmailIMAPFetchResult:
        """
        Synchronously fetch the most recent OTP from Gmail inbox.
        Returns a GmailIMAPFetchResult.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.lookback_hours)

        try:
            imap = self._connect()
        except Exception as exc:
            return GmailIMAPFetchResult(ok=False, error=str(exc))

        try:
            ids = self._collect_candidate_ids(
                imap=imap,
                cutoff=cutoff,
                to_email_contains=to_email_contains,
            )
            if not ids:
                imap.logout()
                return GmailIMAPFetchResult(ok=False, error="No candidate verification emails found")

            ids = ids[-self.max_mails:]
            ids.reverse()  # newest first

            candidates = []
            for msg_id in ids:
                try:
                    typ2, fetched = imap.fetch(msg_id, "(RFC822)")
                    if typ2 != "OK" or not fetched or not fetched[0]:
                        continue
                    raw = fetched[0][1]
                    msg = email_lib.message_from_bytes(raw)

                    subject = _decode_mime(msg.get("Subject", ""))
                    sender = _decode_mime(msg.get("From", ""))
                    to_addr = _decode_mime(msg.get("To", ""))

                    if to_email_contains and to_email_contains.lower() not in to_addr.lower():
                        continue

                    dt = _message_time(msg)
                    if dt < cutoff:
                        continue

                    body = _extract_text(msg)
                    codes = _find_codes(f"{subject}\n{body}")
                    score = _score_message(subject, sender, body)
                    if score <= 0 or not codes:
                        continue

                    candidates.append({
                        "msg_id": msg_id.decode() if isinstance(msg_id, (bytes, bytearray)) else str(msg_id),
                        "score": score,
                        "date": dt,
                        "subject": subject.strip(),
                        "from": sender.strip(),
                        "to": to_addr.strip(),
                        "codes": codes,
                    })
                except Exception as exc:
                    logger.debug("Failed processing message %s: %s", msg_id, exc)
                    continue

            if not candidates:
                imap.logout()
                return GmailIMAPFetchResult(ok=False, error="No verification email found in inbox")

            candidates.sort(key=lambda x: (x["score"], x["date"]), reverse=True)
            best = candidates[0]
            deleted = False

            if delete_best:
                try:
                    imap.store(best["msg_id"], "+FLAGS", "\\Deleted")
                    imap.expunge()
                    deleted = True
                except Exception as exc:
                    logger.warning("Failed to delete message %s: %s", best["msg_id"], exc)

            imap.logout()
            return GmailIMAPFetchResult(
                ok=True,
                best_code=best["codes"][0],
                codes=best["codes"],
                subject=best["subject"],
                sender=best["from"],
                to=best["to"],
                date=best["date"].isoformat(),
                deleted=deleted,
            )
        except Exception as exc:
            try:
                imap.logout()
            except Exception:
                pass
            return GmailIMAPFetchResult(ok=False, error=str(exc))

    async def fetch_latest_code(
        self,
        to_email_contains: str = "",
        delete_best: bool = True,
    ) -> GmailIMAPFetchResult:
        """Async wrapper around fetch_latest_code_sync."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.fetch_latest_code_sync(
                to_email_contains=to_email_contains,
                delete_best=delete_best,
            ),
        )
        return result

    async def wait_for_code(
        self,
        to_email_contains: str = "",
        delete_best: bool = True,
        poll_interval_s: float = 5.0,
        timeout_s: int = 180,
    ) -> GmailIMAPFetchResult:
        """
        Poll until a verification code is found or timeout expires.
        Returns GmailIMAPFetchResult; ok=False on timeout.
        """
        deadline = asyncio.get_event_loop().time() + timeout_s
        attempt = 0
        while True:
            attempt += 1
            result = await self.fetch_latest_code(
                to_email_contains=to_email_contains,
                delete_best=delete_best,
            )
            if result.ok and result.best_code:
                logger.info("Found OTP after %d attempt(s): %s", attempt, result.best_code)
                return result

            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                return GmailIMAPFetchResult(
                    ok=False,
                    error=f"Timeout ({timeout_s}s) waiting for verification code",
                )
            wait = min(poll_interval_s, remaining)
            logger.debug("OTP not found yet (attempt %d), retrying in %.1fs...", attempt, wait)
            await asyncio.sleep(wait)
