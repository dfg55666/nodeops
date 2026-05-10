#!/usr/bin/env python3
"""
NodeOps bridge for Go runtime.

Protocol:
  - Read one request JSON from stdin (plain JSON or B64:<base64-json>).
  - Write JSON lines to stdout as events.

Events:
  {"type":"delta","delta":"..."}
  {"type":"finish","reason":"stop|tool-calls","usage":{...}}
  {"type":"error","message":"...","status_code":...}
"""

from __future__ import annotations

import base64
import json
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from curl_cffi import requests as c_requests
from curl_cffi.const import CurlHttpVersion
from curl_cffi.requests import exceptions as c_exceptions


STDIN_B64_PREFIX = "B64:"
DEFAULT_CONTROL_BASE = "https://stage-vibe-coder-api.nodeops.xyz"
DEFAULT_REFERER = "https://createos.nodeops.network/"
DEFAULT_REFERRAL_URL = "https://nodeops.network"


def _emit(obj: Dict[str, Any]) -> None:
    line = json.dumps(obj, ensure_ascii=False) + "\n"
    sys.stdout.buffer.write(line.encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()


def _read_request_from_stdin() -> Dict[str, Any]:
    raw_bytes = sys.stdin.buffer.read()
    if not raw_bytes or not raw_bytes.strip():
        _emit({"type": "error", "message": "empty stdin", "status_code": 0})
        raise SystemExit(2)

    raw_text = raw_bytes.decode("utf-8", errors="replace").strip()
    if raw_text.startswith(STDIN_B64_PREFIX):
        b64_text = raw_text[len(STDIN_B64_PREFIX) :].strip()
        try:
            decoded_bytes = base64.b64decode(b64_text, validate=True)
            raw_text = decoded_bytes.decode("utf-8")
        except Exception as exc:
            _emit({"type": "error", "message": f"invalid base64 stdin: {exc}", "status_code": 0})
            raise SystemExit(2)

    try:
        req = json.loads(raw_text)
    except Exception as exc:
        _emit({"type": "error", "message": f"invalid json: {exc}", "status_code": 0})
        raise SystemExit(2)
    if not isinstance(req, dict):
        _emit({"type": "error", "message": "stdin json must be an object", "status_code": 0})
        raise SystemExit(2)
    return req


def _json_or_text(resp: c_requests.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        text = (resp.text or "").replace("\r", "").replace("\n", " ")
        return {"raw_text": text[:1200]}


def _is_retryable_curl_error(code: int) -> bool:
    # Common transient transport/protocol failures (HTTP/2 reset/GOAWAY etc.).
    return code in (16, 18, 28, 35, 52, 55, 56, 92)


def _request_with_retry(
    method: str,
    url: str,
    *,
    impersonate: str,
    max_attempts: int = 2,
    **kwargs: Any,
) -> c_requests.Response:
    method = str(method or "GET").upper()
    attempts = max(1, int(max_attempts))
    base_kwargs = dict(kwargs)
    for attempt in range(1, attempts + 1):
        req_kwargs = dict(base_kwargs)
        if attempt > 1:
            # Fallback to HTTP/1.1 on retry to avoid flaky H2 transport errors.
            req_kwargs["http_version"] = CurlHttpVersion.V1_1
            headers = dict(req_kwargs.get("headers") or {})
            headers["Connection"] = "close"
            req_kwargs["headers"] = headers
        try:
            return c_requests.request(method, url, impersonate=impersonate, **req_kwargs)
        except c_exceptions.RequestException as exc:
            code = int(getattr(exc, "code", 0) or 0)
            if attempt >= attempts or not _is_retryable_curl_error(code):
                raise
            time.sleep(min(0.2 * attempt, 0.8))
    raise RuntimeError("unreachable")


def _transport_error(label: str, exc: Exception) -> RuntimeError:
    code = int(getattr(exc, "code", 0) or 0)
    return RuntimeError(f"{label} transport failed (curl:{code}): {exc}")


def _control_headers(auth_token: str) -> Dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Referer": DEFAULT_REFERER,
        "ReferralURL": DEFAULT_REFERRAL_URL,
        "X-Auth-Token": auth_token,
    }


def _runtime_headers(project_token: str, *, with_json_content_type: bool = True) -> Dict[str, str]:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": DEFAULT_REFERER,
        "x-project-token": project_token,
    }
    if with_json_content_type:
        headers["Content-Type"] = "application/json"
    return headers


def _safe_lower(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _emit_runtime_state(
    deployment_id: str,
    endpoint: str,
    project_token: str,
    active_session_id: str,
    standby_session_id: str,
) -> None:
    _emit(
        {
            "type": "runtime_state",
            "deployment_id": str(deployment_id or "").strip(),
            "runtime_endpoint": str(endpoint or "").strip().rstrip("/"),
            "project_token": str(project_token or "").strip(),
            "active_session_id": str(active_session_id or "").strip(),
            "standby_session_id": str(standby_session_id or "").strip(),
            "session_id": str(standby_session_id or active_session_id or "").strip(),
        }
    )


def _should_reset_runtime(exc: Exception) -> bool:
    text = _safe_lower(exc)
    markers = (
        "auth failed",
        "unauthorized",
        "forbidden",
        "status 401",
        "status 403",
        "status 404",
        "post message failed (404)",
        "post message transport failed",
        "unconfirmed",
        "poll auth failed",
    )
    return any(marker in text for marker in markers)


def _extract_deployment(payload: Dict[str, Any]) -> Tuple[str, str, str, str]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        data = {}
    deployment_id = str(data.get("id") or "").strip()
    endpoint = str(data.get("server_endpoint") or "").strip().rstrip("/")
    token = str(data.get("token") or "").strip()
    request_id = str(data.get("request_id") or data.get("requestId") or "").strip()
    return deployment_id, endpoint, token, request_id


def _create_or_wait_deployment(
    control_base: str,
    auth_token: str,
    deployment_prompt: str,
    impersonate: str,
    verify: bool,
    timeout_s: int,
    poll_interval_s: float,
    poll_timeout_s: int,
) -> Tuple[str, str, str]:
    create_url = f"{control_base.rstrip('/')}/api/v1/deployments"
    try:
        resp = _request_with_retry(
            "POST",
            create_url,
            headers=_control_headers(auth_token),
            json={"prompt": deployment_prompt},
            timeout=timeout_s,
            impersonate=impersonate,
            verify=verify,
            max_attempts=3,
        )
    except c_exceptions.RequestException as exc:
        raise _transport_error("create deployment", exc) from exc
    payload = _json_or_text(resp)
    payload_obj = payload if isinstance(payload, dict) else {"raw": payload}
    if resp.status_code >= 400:
        raise RuntimeError(f"create deployment failed ({resp.status_code}): {payload_obj}")

    deployment_id, endpoint, project_token, request_id = _extract_deployment(payload_obj)
    if deployment_id and endpoint and project_token:
        return deployment_id, endpoint, project_token

    if not request_id and resp.status_code != 202:
        raise RuntimeError(f"deployment response missing endpoint/token/request_id: {payload_obj}")

    if not request_id:
        raise RuntimeError(f"deployment queued but request_id missing: {payload_obj}")

    deadline = time.time() + max(5, int(poll_timeout_s))
    poll_url = f"{control_base.rstrip('/')}/api/v1/deployments/{request_id}"
    while time.time() < deadline:
        try:
            poll_resp = _request_with_retry(
                "GET",
                poll_url,
                headers=_control_headers(auth_token),
                timeout=timeout_s,
                impersonate=impersonate,
                verify=verify,
                max_attempts=3,
            )
        except c_exceptions.RequestException:
            time.sleep(max(0.3, float(poll_interval_s)))
            continue
        poll_payload = _json_or_text(poll_resp)
        poll_obj = poll_payload if isinstance(poll_payload, dict) else {"raw": poll_payload}
        deployment_id, endpoint, project_token, _ = _extract_deployment(poll_obj)
        if deployment_id and endpoint and project_token:
            return deployment_id, endpoint, project_token

        state = ""
        data = poll_obj.get("data")
        if isinstance(data, dict):
            state = _safe_lower(data.get("status"))
            if not state:
                state = _safe_lower(data.get("state"))
            msg = _safe_lower(data.get("message"))
        else:
            msg = ""
        if not state:
            state = _safe_lower(poll_obj.get("status"))
        if "fail" in state or "error" in state or "failed" in msg:
            raise RuntimeError(f"queued deployment failed: state={state}, payload={poll_obj}")

        time.sleep(max(0.3, float(poll_interval_s)))

    raise RuntimeError(f"queued deployment timeout: request_id={request_id}")


def _create_session(
    endpoint: str,
    project_token: str,
    session_title: str,
    impersonate: str,
    verify: bool,
    timeout_s: int,
) -> str:
    session_url = f"{endpoint.rstrip('/')}/session"
    max_session_attempts = 8
    for attempt in range(1, max_session_attempts + 1):
        try:
            resp = _request_with_retry(
                "POST",
                session_url,
                headers=_runtime_headers(project_token, with_json_content_type=True),
                json={"title": session_title},
                timeout=timeout_s,
                impersonate=impersonate,
                verify=verify,
                max_attempts=3,
            )
        except c_exceptions.RequestException as exc:
            if attempt >= max_session_attempts:
                raise _transport_error("create session", exc) from exc
            time.sleep(min(0.6 * attempt, 2.5))
            continue

        payload = _json_or_text(resp)
        if resp.status_code in (200, 201):
            if not isinstance(payload, dict):
                raise RuntimeError(f"create session bad payload: {payload}")
            sid = str(payload.get("id") or "").strip()
            if not sid:
                raise RuntimeError(f"create session missing id: {payload}")
            return sid

        if resp.status_code in (401, 403):
            raise RuntimeError(f"create session auth failed ({resp.status_code}): {payload}")
        if resp.status_code in (404, 429, 500, 502, 503, 504):
            if attempt < max_session_attempts:
                time.sleep(min(0.6 * attempt, 2.5))
                continue
        raise RuntimeError(f"create session failed ({resp.status_code}): {payload}")

    raise RuntimeError("create session failed: retries exhausted")


def _post_message(
    endpoint: str,
    session_id: str,
    project_token: str,
    prompt: str,
    model_id: str,
    impersonate: str,
    verify: bool,
    timeout_s: int,
    post_confirm_timeout_s: float = 12.0,
    post_confirm_interval_s: float = 0.6,
) -> None:
    post_url = f"{endpoint.rstrip('/')}/session/{session_id}/message"
    body = {
        "model": {"providerID": "openrouter", "modelID": model_id},
        "parts": [{"type": "text", "text": prompt}],
        "system": "",
    }

    baseline_count: Optional[int] = None
    baseline_timeout_s = min(max(5, int(timeout_s)), 15)
    try:
        baseline_count = len(
            _fetch_messages(
                endpoint=endpoint,
                session_id=session_id,
                project_token=project_token,
                impersonate=impersonate,
                verify=verify,
                timeout_s=baseline_timeout_s,
            )
        )
    except Exception as exc:
        if _should_reset_runtime(exc):
            raise
        baseline_count = None

    fingerprint = _tail_fingerprint(prompt)

    def _confirm_posted() -> bool:
        confirm_timeout_s = float(post_confirm_timeout_s)
        if confirm_timeout_s <= 0:
            return False

        interval_s = float(post_confirm_interval_s)
        if interval_s <= 0:
            interval_s = 0.6
        interval_s = max(0.2, interval_s)

        deadline = time.time() + confirm_timeout_s
        while time.time() < deadline:
            try:
                messages = _fetch_messages(
                    endpoint=endpoint,
                    session_id=session_id,
                    project_token=project_token,
                    impersonate=impersonate,
                    verify=verify,
                    timeout_s=baseline_timeout_s,
                )
            except Exception:
                time.sleep(interval_s)
                continue

            if baseline_count is not None and len(messages) >= baseline_count+1:
                return True
            if _contains_user_fingerprint(messages, fingerprint):
                return True

            time.sleep(interval_s)
        return False

    try:
        resp = _request_with_retry(
            "POST",
            post_url,
            headers=_runtime_headers(project_token, with_json_content_type=True),
            json=body,
            timeout=timeout_s,
            impersonate=impersonate,
            verify=verify,
            max_attempts=3,
        )
    except c_exceptions.RequestException as exc:
        # For large prompts, edge/proxy can drop the connection after the upstream
        # already accepted the message. Confirm by polling; otherwise fail fast.
        if _confirm_posted():
            return
        raise _transport_error("post message", exc) from exc

    if resp.status_code in (200, 201, 202):
        return

    payload = _json_or_text(resp)
    if resp.status_code in (401, 403):
        raise RuntimeError(f"post message auth failed ({resp.status_code}): {payload}")
    if resp.status_code == 429:
        raise RuntimeError(f"post message rate limited ({resp.status_code}): {payload}")
    if resp.status_code >= 500:
        # Cloudflare/edge errors on POST do not reliably indicate the message was rejected.
        # Confirm by checking whether the user message landed before giving up.
        if _confirm_posted():
            return
        raise RuntimeError(f"post message failed ({resp.status_code}): {payload} (unconfirmed)")

    raise RuntimeError(f"post message failed ({resp.status_code}): {payload}")


def _extract_text(parts: Any) -> str:
    if not isinstance(parts, list):
        return ""
    out: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        if str(part.get("type") or "").strip().lower() == "text":
            out.append(str(part.get("text") or ""))
    return "".join(out)


def _normalize_message_list(payload: Any) -> List[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("raw"), list):
        # Backward compatibility if list payload was wrapped as {"raw": [...]}
        return payload.get("raw") or []
    return []


def _normalize_compact_text(text: str) -> str:
    cleaned = str(text or "").replace("\r", "").replace("\n", " ")
    return " ".join(cleaned.split())


def _tail_fingerprint(text: str, max_chars: int = 180) -> str:
    cleaned = _normalize_compact_text(text)
    if max_chars <= 0:
        return cleaned
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[-max_chars:]


def _fetch_messages(
    endpoint: str,
    session_id: str,
    project_token: str,
    impersonate: str,
    verify: bool,
    timeout_s: int,
) -> List[Any]:
    poll_url = f"{endpoint.rstrip('/')}/session/{session_id}/message"
    try:
        resp = _request_with_retry(
            "GET",
            poll_url,
            params={"_": int(time.time() * 1000)},
            headers=_runtime_headers(project_token, with_json_content_type=False),
            timeout=timeout_s,
            impersonate=impersonate,
            verify=verify,
            max_attempts=3,
        )
    except c_exceptions.RequestException as exc:
        raise _transport_error("poll message", exc) from exc

    payload = _json_or_text(resp)
    if resp.status_code >= 400:
        if resp.status_code in (401, 403):
            raise RuntimeError(f"poll auth failed ({resp.status_code}): {payload}")
        if resp.status_code == 429:
            raise RuntimeError(f"poll rate limited ({resp.status_code}): {payload}")
        raise RuntimeError(f"poll failed ({resp.status_code}): {payload}")

    return _normalize_message_list(payload)


def _contains_user_fingerprint(messages: List[Any], fingerprint: str) -> bool:
    if not fingerprint:
        return False
    for msg in reversed(messages):
        if not isinstance(msg, dict):
            continue
        info = msg.get("info")
        if isinstance(info, dict) and _safe_lower(info.get("role")) == "user":
            user_text = _normalize_compact_text(_extract_text(msg.get("parts")))
            if fingerprint in user_text:
                return True
    return False


def _poll_and_stream(
    endpoint: str,
    session_id: str,
    project_token: str,
    impersonate: str,
    verify: bool,
    timeout_s: int,
    poll_interval_s: float,
    poll_timeout_s: int,
    poll_max_interval_s: float = 0.0,
    poll_no_first_token_grace_s: float = 25.0,
    poll_stall_grace_s: float = 20.0,
    poll_backoff_factor: float = 1.6,
) -> None:
    poll_url = f"{endpoint.rstrip('/')}/session/{session_id}/message"
    deadline = time.time() + max(10, int(poll_timeout_s))
    last_text = ""
    transport_failures = 0

    base_interval_s = max(0.3, float(poll_interval_s))
    max_interval_s = float(poll_max_interval_s or 0.0)
    if max_interval_s <= 0:
        max_interval_s = max(base_interval_s, 30.0)
    else:
        max_interval_s = max(base_interval_s, max_interval_s)

    no_first_token_grace_s = float(poll_no_first_token_grace_s)
    if no_first_token_grace_s < 0:
        no_first_token_grace_s = 25.0

    stall_grace_s = float(poll_stall_grace_s)
    if stall_grace_s < 0:
        stall_grace_s = 20.0

    backoff_factor = float(poll_backoff_factor)
    if backoff_factor <= 1.0:
        backoff_factor = 1.6

    started_at = time.time()
    last_progress_at = started_at
    current_interval_s = base_interval_s
    observed_first_token = False

    def _on_progress(now_ts: float) -> None:
        nonlocal observed_first_token, last_progress_at, current_interval_s
        observed_first_token = True
        last_progress_at = now_ts
        current_interval_s = base_interval_s

    def _on_rate_limited() -> None:
        nonlocal current_interval_s
        current_interval_s = max_interval_s

    def _on_no_progress(now_ts: float) -> None:
        nonlocal current_interval_s
        if not observed_first_token:
            if now_ts - started_at <= no_first_token_grace_s:
                current_interval_s = base_interval_s
                return
        else:
            if now_ts - last_progress_at <= stall_grace_s:
                current_interval_s = base_interval_s
                return

        next_interval = max(base_interval_s, current_interval_s * backoff_factor)
        current_interval_s = min(max_interval_s, next_interval)

    while time.time() < deadline:
        now_ts = time.time()
        try:
            resp = _request_with_retry(
                "GET",
                poll_url,
                params={"_": int(time.time() * 1000)},
                headers=_runtime_headers(project_token, with_json_content_type=False),
                timeout=timeout_s,
                impersonate=impersonate,
                verify=verify,
                max_attempts=3,
            )
            transport_failures = 0
        except c_exceptions.RequestException as exc:
            code = int(getattr(exc, "code", 0) or 0)
            if _is_retryable_curl_error(code):
                transport_failures += 1
                if transport_failures >= 8:
                    raise _transport_error("poll message", exc) from exc
                _on_no_progress(now_ts)
                time.sleep(max(0.3, float(current_interval_s)))
                continue
            raise _transport_error("poll message", exc) from exc
        payload = _json_or_text(resp)
        if resp.status_code >= 400:
            if resp.status_code in (401, 403):
                raise RuntimeError(f"poll auth failed ({resp.status_code}): {payload}")
            if resp.status_code == 429:
                _on_rate_limited()
            else:
                _on_no_progress(now_ts)
            time.sleep(max(0.3, float(current_interval_s)))
            continue

        messages = _normalize_message_list(payload)
        assistant: Optional[Dict[str, Any]] = None
        for msg in reversed(messages):
            if not isinstance(msg, dict):
                continue
            info = msg.get("info")
            if isinstance(info, dict) and _safe_lower(info.get("role")) == "assistant":
                assistant = msg
                break

        if not assistant:
            _on_no_progress(now_ts)
            time.sleep(max(0.3, float(current_interval_s)))
            continue

        info = assistant.get("info") if isinstance(assistant.get("info"), dict) else {}
        err_obj = info.get("error") if isinstance(info, dict) else None
        if isinstance(err_obj, dict) and err_obj:
            err_name = str(err_obj.get("name") or "").strip()
            err_data = err_obj.get("data") if isinstance(err_obj.get("data"), dict) else {}
            err_msg = str(err_data.get("message") or err_name or "unknown upstream error").strip()
            status_code = int(err_data.get("statusCode") or 0)
            _emit({"type": "error", "message": err_msg, "status_code": status_code})
            raise SystemExit(1)

        current_text = _extract_text(assistant.get("parts"))
        progressed = False
        if len(current_text) > len(last_text):
            delta = current_text[len(last_text) :]
            _emit({"type": "delta", "delta": delta})
            last_text = current_text
            progressed = True

        if progressed:
            _on_progress(now_ts)
        else:
            _on_no_progress(now_ts)

        finish = _safe_lower(info.get("finish")) if isinstance(info, dict) else ""
        if finish in {"stop", "tool-calls"}:
            usage_obj = info.get("tokens")
            usage = usage_obj if isinstance(usage_obj, dict) else {}
            _emit({"type": "finish", "reason": finish, "usage": usage})
            return

        time.sleep(max(0.3, float(current_interval_s)))

    raise RuntimeError("poll timeout")


def _run_chat(req: Dict[str, Any]) -> int:
    auth_token = str(req.get("auth_token") or "").strip()
    if not auth_token:
        _emit({"type": "error", "message": "auth_token is empty", "status_code": 0})
        return 2

    prompt = str(req.get("prompt") or "").strip() or "hi"
    model_id = str(req.get("model_id") or "").strip()
    if not model_id:
        _emit({"type": "error", "message": "model_id is empty", "status_code": 0})
        return 2

    control_base = str(req.get("control_base_url") or DEFAULT_CONTROL_BASE).strip().rstrip("/")
    if control_base.endswith("/api/v1"):
        control_base = control_base[: -len("/api/v1")]
    if not control_base.startswith("http"):
        control_base = DEFAULT_CONTROL_BASE

    deployment_prompt = str(req.get("deployment_prompt") or "init").strip() or "init"
    session_title = str(req.get("session_title") or "orchids-proxy").strip() or "orchids-proxy"
    impersonate = str(req.get("impersonate") or "chrome124").strip() or "chrome124"
    insecure = bool(req.get("insecure"))
    verify = not insecure
    timeout_s = int(req.get("timeout_s") or 90)
    poll_interval_s = float(req.get("poll_interval_s") or 2.5)
    poll_timeout_s = int(req.get("poll_timeout_s") or 600)
    raw_poll_max_interval_s = req.get("poll_max_interval_s")
    poll_max_interval_s = float(raw_poll_max_interval_s) if raw_poll_max_interval_s is not None else 0.0
    raw_poll_no_first_token_grace_s = req.get("poll_no_first_token_grace_s")
    poll_no_first_token_grace_s = (
        float(raw_poll_no_first_token_grace_s) if raw_poll_no_first_token_grace_s is not None else 25.0
    )
    raw_poll_stall_grace_s = req.get("poll_stall_grace_s")
    poll_stall_grace_s = float(raw_poll_stall_grace_s) if raw_poll_stall_grace_s is not None else 20.0
    raw_poll_backoff_factor = req.get("poll_backoff_factor")
    poll_backoff_factor = float(raw_poll_backoff_factor) if raw_poll_backoff_factor is not None else 1.6
    prepare_standby = bool(req.get("prepare_standby", True))

    raw_post_confirm_timeout_s = req.get("post_confirm_timeout_s")
    post_confirm_timeout_s = float(raw_post_confirm_timeout_s) if raw_post_confirm_timeout_s is not None else 12.0
    raw_post_confirm_interval_s = req.get("post_confirm_interval_s")
    post_confirm_interval_s = (
        float(raw_post_confirm_interval_s) if raw_post_confirm_interval_s is not None else 0.6
    )

    endpoint = str(req.get("runtime_endpoint") or "").strip().rstrip("/")
    project_token = str(req.get("project_token") or "").strip()
    session_id = str(req.get("session_id") or "").strip()
    deployment_id = str(req.get("deployment_id") or "").strip()

    try:
        if not endpoint or not project_token:
            deployment_id, endpoint, project_token = _create_or_wait_deployment(
                control_base=control_base,
                auth_token=auth_token,
                deployment_prompt=deployment_prompt,
                impersonate=impersonate,
                verify=verify,
                timeout_s=timeout_s,
                poll_interval_s=poll_interval_s,
                poll_timeout_s=min(max(poll_timeout_s, 30), 900),
            )
            session_id = ""

        if not session_id:
            session_id = _create_session(
                endpoint=endpoint,
                project_token=project_token,
                session_title=session_title,
                impersonate=impersonate,
                verify=verify,
                timeout_s=timeout_s,
            )

        for attempt in range(1, 3):
            try:
                _post_message(
                    endpoint=endpoint,
                    session_id=session_id,
                    project_token=project_token,
                    prompt=prompt,
                    model_id=model_id,
                    impersonate=impersonate,
                    verify=verify,
                    timeout_s=timeout_s,
                    post_confirm_timeout_s=post_confirm_timeout_s,
                    post_confirm_interval_s=post_confirm_interval_s,
                )
                _poll_and_stream(
                    endpoint=endpoint,
                    session_id=session_id,
                    project_token=project_token,
                    impersonate=impersonate,
                    verify=verify,
                    timeout_s=timeout_s,
                    poll_interval_s=poll_interval_s,
                    poll_timeout_s=min(max(poll_timeout_s, 30), 900),
                    poll_max_interval_s=poll_max_interval_s,
                    poll_no_first_token_grace_s=poll_no_first_token_grace_s,
                    poll_stall_grace_s=poll_stall_grace_s,
                    poll_backoff_factor=poll_backoff_factor,
                )
                break
            except Exception as req_exc:
                if attempt >= 2 or not _should_reset_runtime(req_exc):
                    raise
                deployment_id, endpoint, project_token = _create_or_wait_deployment(
                    control_base=control_base,
                    auth_token=auth_token,
                    deployment_prompt=deployment_prompt,
                    impersonate=impersonate,
                    verify=verify,
                    timeout_s=timeout_s,
                    poll_interval_s=poll_interval_s,
                    poll_timeout_s=min(max(poll_timeout_s, 30), 900),
                )
                session_id = _create_session(
                    endpoint=endpoint,
                    project_token=project_token,
                    session_title=session_title,
                    impersonate=impersonate,
                    verify=verify,
                    timeout_s=timeout_s,
                )

        standby_session_id = session_id
        if prepare_standby:
            try:
                standby_session_id = _create_session(
                    endpoint=endpoint,
                    project_token=project_token,
                    session_title=session_title,
                    impersonate=impersonate,
                    verify=verify,
                    timeout_s=timeout_s,
                )
            except Exception:
                standby_session_id = session_id

        _emit_runtime_state(deployment_id, endpoint, project_token, session_id, standby_session_id)
        return 0
    except Exception as exc:
        _emit({"type": "error", "message": str(exc), "status_code": 0})
        return 1


def main() -> int:
    req = _read_request_from_stdin()
    action = str(req.get("action") or "").strip().lower()
    if action != "chat":
        _emit({"type": "error", "message": f"unsupported action: {action}", "status_code": 0})
        return 2
    return _run_chat(req)


if __name__ == "__main__":
    raise SystemExit(main())
