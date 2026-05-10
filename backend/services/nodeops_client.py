"""
NodeOps CreateOS API client.

Layered API:
  1. Auth       — oneclick-backend.nodeops.xyz
  2. Credits    — api-createos.nodeops.network
  3. Control    — stage-vibe-coder-api.nodeops.xyz
  4. Runtime    — dynamic *.orak.nodeops.app
"""
import asyncio
import logging
import time
from typing import Any, AsyncIterator
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

AUTH_BASE = "https://oneclick-backend.nodeops.xyz/api/v1"
CREDITS_BASE = "https://api-createos.nodeops.network/v1"
CONTROL_BASE = "https://stage-vibe-coder-api.nodeops.xyz/api/v1"

DEFAULT_CREDIT_SKU_ID = "00000000-0000-0000-0000-000000000007"

COMMON_HEADERS = {
    "Content-Type": "application/json",
    "ReferralURL": "https://nodeops.network",
    "Accept": "application/json, text/plain, */*",
}

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client


async def close_client():
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


def _auth_headers(auth_token: str) -> dict[str, str]:
    return {**COMMON_HEADERS, "X-Auth-Token": auth_token}


def _runtime_headers(project_token: str, ygg_token: str) -> dict[str, str]:
    # Runtime API requires x-project-token and y-gg-token.
    # The frontend/runtime currently accepts different y-gg-token sources
    # (project token or auth token) depending on route/runtime cluster.
    return {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "x-project-token": project_token,
        "y-gg-token": ygg_token,
    }


def _runtime_base(runtime_host_or_url: str) -> str:
    value = str(runtime_host_or_url or "").strip().rstrip("/")
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"https://{value}"


def _unwrap_data(payload: Any) -> Any:
    if isinstance(payload, dict):
        data = payload.get("data")
        if data is not None:
            return data
    return payload


def _parse_json(resp: httpx.Response) -> Any:
    if not resp.content:
        return {}
    try:
        return resp.json()
    except ValueError:
        return {"raw_text": resp.text}


def _guess_mime_from_data_url(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw.startswith("data:"):
        return None
    # data:<mime>;base64,....
    head = raw.split(",", 1)[0]
    mime = head[5:].split(";", 1)[0].strip()
    return mime or None


def _normalize_model_payload(model: Any) -> dict[str, str] | None:
    """
    Runtime `/session/{id}/message` expects:
      model: { providerID: "...", modelID: "..." }

    For backward compatibility we still accept string model IDs and map them
    to openrouter provider.
    """
    if model is None:
        return None
    if isinstance(model, str):
        model_id = model.strip()
        if not model_id:
            return None
        return {"providerID": "openrouter", "modelID": model_id}
    if isinstance(model, dict):
        provider_id = str(model.get("providerID") or model.get("provider_id") or "").strip() or "openrouter"
        model_id = str(model.get("modelID") or model.get("model_id") or "").strip()
        if not model_id:
            return None
        return {"providerID": provider_id, "modelID": model_id}
    return None


def _runtime_ygg_candidates(
    project_token: str,
    auth_token: str,
    preferred_ygg: str | None = None,
) -> list[str]:
    candidates: list[str] = []
    for raw in (preferred_ygg, auth_token, project_token):
        token = str(raw or "").strip()
        if token and token not in candidates:
            candidates.append(token)
    return candidates


def _is_runtime_auth_failure(resp: httpx.Response) -> bool:
    if resp.status_code in (401, 403):
        return True
    text = str(resp.text or "").lower()
    if not text:
        return False
    return any(
        marker in text
        for marker in (
            "failed jwt authentication",
            "jwt not yet valid",
            "wrong requirement_name",
            "unauthorized",
            "token",
        )
    )


async def _runtime_request(
    method: str,
    runtime_host: str,
    project_token: str,
    auth_token: str,
    path: str,
    *,
    preferred_ygg: str | None = None,
    retries: int = 3,
    **kwargs,
) -> httpx.Response:
    url = f"{_runtime_base(runtime_host)}{path}"
    last_resp: httpx.Response | None = None
    ygg_candidates = _runtime_ygg_candidates(project_token, auth_token, preferred_ygg)

    if not ygg_candidates:
        raise RuntimeError("No runtime token candidates available for y-gg-token")

    for idx, ygg_token in enumerate(ygg_candidates):
        resp = await _retry_request(
            method,
            url,
            retries=retries,
            headers=_runtime_headers(project_token, ygg_token),
            **kwargs,
        )
        last_resp = resp

        # Success path
        if resp.status_code < 400:
            return resp

        # Retry with alternate y-gg-token only for auth-style failures.
        has_next = idx < len(ygg_candidates) - 1
        if has_next and _is_runtime_auth_failure(resp):
            logger.warning(
                "Runtime %s %s auth failed with y-gg candidate #%s (status=%s), trying alternate token",
                method,
                path,
                idx + 1,
                resp.status_code,
            )
            continue

        return resp

    # Should not happen because loop returns above, but keep safe.
    if last_resp is None:
        raise RuntimeError(f"Runtime request failed without response: {method} {url}")
    return last_resp


async def _retry_request(method: str, url: str, retries: int = 3, **kwargs) -> httpx.Response:
    """
    Execute request with retry for transient failures.
    Retries on network errors, 429 and 5xx.
    """
    client = get_client()
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = await client.request(method, url, **kwargs)
            if resp.status_code < 500 and resp.status_code != 429:
                return resp
            last_exc = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:400]}")
            logger.warning(
                "Retry %s/%s for %s %s: %s",
                attempt + 1, retries, method, url, resp.status_code
            )
        except httpx.HTTPError as exc:
            last_exc = exc
            logger.warning(
                "Retry %s/%s for %s %s: %s",
                attempt + 1, retries, method, url, exc
            )
        if attempt < retries - 1:
            await asyncio.sleep(2 ** attempt)
    if last_exc is None:
        last_exc = RuntimeError(f"Request failed without response: {method} {url}")
    raise last_exc


# ─── 1. Auth Layer ──────────────────────────────────────────────────

async def login(email: str) -> dict:
    """
    POST /api/v1/login — trigger OTP.
    Captured payload includes {"email", "from":"createos"}.
    """
    resp = await _retry_request(
        "POST",
        f"{AUTH_BASE}/login",
        headers=COMMON_HEADERS,
        json={"email": email, "from": "createos"},
    )
    resp.raise_for_status()
    payload = _parse_json(resp)
    return payload if isinstance(payload, dict) else {"data": payload}


async def verify_otp(email: str, otp: str) -> dict:
    """
    POST /api/v1/login/verify — verify otp.
    Captured payload uses key "otp".
    """
    resp = await _retry_request(
        "POST",
        f"{AUTH_BASE}/login/verify",
        headers=COMMON_HEADERS,
        json={"email": email, "otp": otp},
    )
    resp.raise_for_status()
    payload = _parse_json(resp)
    return payload if isinstance(payload, dict) else {"data": payload}


# ─── 2. Credits Layer ───────────────────────────────────────────────

async def get_credits(auth_token: str) -> dict:
    resp = await _retry_request(
        "GET",
        f"{CREDITS_BASE}/credits",
        headers=_auth_headers(auth_token),
    )
    resp.raise_for_status()
    payload = _parse_json(resp)
    return payload if isinstance(payload, dict) else {"data": payload}


async def get_topup_settings(auth_token: str) -> dict:
    resp = await _retry_request(
        "GET",
        f"{CREDITS_BASE}/credits/openrouter/topup-settings",
        headers=_auth_headers(auth_token),
    )
    resp.raise_for_status()
    payload = _parse_json(resp)
    return payload if isinstance(payload, dict) else {"data": payload}


async def topup_credits(auth_token: str, payload: dict) -> dict:
    resp = await _retry_request(
        "POST",
        f"{CREDITS_BASE}/credits/openrouter",
        headers=_auth_headers(auth_token),
        json=payload,
    )
    resp.raise_for_status()
    data = _parse_json(resp)
    return data if isinstance(data, dict) else {"data": data}


async def get_credit_conversion_rate(
    auth_token: str,
    sku_id: str = DEFAULT_CREDIT_SKU_ID,
    amount: int = 1,
    payment_method: str = "checkout",
) -> dict:
    resp = await _retry_request(
        "GET",
        f"{CREDITS_BASE}/payments/credit-conversion-rate",
        headers=_auth_headers(auth_token),
        params={
            "skuId": sku_id,
            "creditMultiplier": 1,
            "amount": amount,
            "paymentMethod": payment_method,
        },
    )
    resp.raise_for_status()
    data = _parse_json(resp)
    return data if isinstance(data, dict) else {"data": data}


async def get_credit_skus(auth_token: str) -> dict:
    resp = await _retry_request(
        "GET",
        f"{CREDITS_BASE}/skus/credit",
        headers=_auth_headers(auth_token),
    )
    resp.raise_for_status()
    data = _parse_json(resp)
    return data if isinstance(data, dict) else {"data": data}


# ─── 3. Control Plane ───────────────────────────────────────────────

async def list_deployments(auth_token: str) -> dict:
    resp = await _retry_request(
        "GET",
        f"{CONTROL_BASE}/deployments",
        headers=_auth_headers(auth_token),
    )
    resp.raise_for_status()
    data = _parse_json(resp)
    return data if isinstance(data, dict) else {"data": data}


async def create_deployment(auth_token: str, prompt: str = "init") -> dict:
    """
    Prefer latest endpoint /deployments/pi-agent.
    """
    headers = _auth_headers(auth_token)
    try:
        resp = await _retry_request(
            "POST",
            f"{CONTROL_BASE}/deployments/pi-agent",
            headers=headers,
            json={"prompt": str(prompt or "init")},
        )
        if resp.status_code not in (200, 201, 202):
            resp.raise_for_status()
        data = _parse_json(resp)
        return data if isinstance(data, dict) else {"data": data}
    except Exception as pi_agent_exc:
        # Backward compatibility fallback used by earlier captures/scripts.
        logger.warning("create_deployment via /pi-agent failed, fallback to /deployments: %s", pi_agent_exc)
        resp = await _retry_request(
            "POST",
            f"{CONTROL_BASE}/deployments",
            headers=headers,
            json={"prompt": str(prompt or "init")},
        )
        if resp.status_code not in (200, 201, 202):
            resp.raise_for_status()
        data = _parse_json(resp)
        return data if isinstance(data, dict) else {"data": data}


async def get_deployment(auth_token: str, deployment_id: str) -> dict:
    resp = await _retry_request(
        "GET",
        f"{CONTROL_BASE}/deployments/{deployment_id}",
        headers=_auth_headers(auth_token),
    )
    resp.raise_for_status()
    data = _parse_json(resp)
    return data if isinstance(data, dict) else {"data": data}


async def get_usage(auth_token: str) -> dict:
    resp = await _retry_request(
        "GET",
        f"{CONTROL_BASE}/usage",
        headers=_auth_headers(auth_token),
    )
    resp.raise_for_status()
    data = _parse_json(resp)
    return data if isinstance(data, dict) else {"data": data}


# ─── 4. Runtime Layer ───────────────────────────────────────────────

async def create_session(
    runtime_host: str,
    project_token: str,
    auth_token: str,
    title: str | None = None,
    model: str | None = None,
) -> dict:
    body: dict[str, Any] = {}
    if title:
        body["title"] = title
    if model:
        body["model"] = model
    resp = await _runtime_request(
        "POST",
        runtime_host,
        project_token,
        auth_token,
        "/session",
        json=body,
    )
    resp.raise_for_status()
    payload = _parse_json(resp)
    unwrapped = _unwrap_data(payload)
    return unwrapped if isinstance(unwrapped, dict) else (payload if isinstance(payload, dict) else {"data": payload})


async def list_sessions(runtime_host: str, project_token: str, auth_token: str) -> Any:
    resp = await _runtime_request(
        "GET",
        runtime_host,
        project_token,
        auth_token,
        "/session",
    )
    resp.raise_for_status()
    payload = _parse_json(resp)
    return _unwrap_data(payload)


async def send_message(
    runtime_host: str,
    project_token: str,
    auth_token: str,
    session_id: str,
    text: str,
    no_reply: bool = False,
    system: str | None = None,
    model: Any | None = None,
    agent: str | None = None,
    image_url: str | None = None,
    image_mime: str | None = None,
) -> Any:
    parts: list[dict[str, Any]] = []
    if str(text or "").strip():
        parts.append({"type": "text", "text": str(text)})
    if str(image_url or "").strip():
        mime = str(image_mime or "").strip() or _guess_mime_from_data_url(image_url) or "image/png"
        parts.append({"type": "file", "mime": mime, "url": str(image_url)})
    if not parts:
        raise ValueError("send_message requires non-empty text or image_url")

    body: dict[str, Any] = {
        "parts": parts,
        "noReply": no_reply,
    }
    if system:
        body["system"] = system
    model_payload = _normalize_model_payload(model)
    if model_payload:
        body["model"] = model_payload
    if agent:
        body["agent"] = agent

    resp = await _runtime_request(
        "POST",
        runtime_host,
        project_token,
        auth_token,
        f"/session/{session_id}/message",
        json=body,
    )
    resp.raise_for_status()
    payload = _parse_json(resp)
    return _unwrap_data(payload)


async def get_messages(
    runtime_host: str,
    project_token: str,
    auth_token: str,
    session_id: str,
) -> Any:
    resp = await _runtime_request(
        "GET",
        runtime_host,
        project_token,
        auth_token,
        f"/session/{session_id}/message",
        params={"_": int(time.time() * 1000)},
    )
    resp.raise_for_status()
    payload = _parse_json(resp)
    return _unwrap_data(payload)


async def get_session_context(
    runtime_host: str,
    project_token: str,
    auth_token: str,
    session_id: str,
) -> Any:
    resp = await _runtime_request(
        "GET",
        runtime_host,
        project_token,
        auth_token,
        f"/session/{session_id}/context",
    )
    resp.raise_for_status()
    payload = _parse_json(resp)
    return _unwrap_data(payload)


async def get_subagents(
    runtime_host: str,
    project_token: str,
    auth_token: str,
    session_id: str,
) -> Any:
    resp = await _runtime_request(
        "GET",
        runtime_host,
        project_token,
        auth_token,
        f"/session/{session_id}/subagents",
    )
    resp.raise_for_status()
    payload = _parse_json(resp)
    return _unwrap_data(payload)


async def abort_session(
    runtime_host: str,
    project_token: str,
    auth_token: str,
    session_id: str,
) -> Any:
    resp = await _runtime_request(
        "POST",
        runtime_host,
        project_token,
        auth_token,
        f"/session/{session_id}/abort",
        json={},
    )
    resp.raise_for_status()
    payload = _parse_json(resp)
    return _unwrap_data(payload)


async def connect_sse(runtime_host: str, token: str, session_id: str) -> AsyncIterator[str]:
    url = f"{_runtime_base(runtime_host)}/session/{session_id}/event?token={quote(token, safe='')}"
    client = get_client()
    async with client.stream(
        "GET",
        url,
        headers={
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
        },
        timeout=None,
    ) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            yield line


# ─── Runtime: File operations ───────────────────────────────────────

async def get_file_tree(
    runtime_host: str,
    project_token: str,
    auth_token: str,
    path: str = "",
) -> Any:
    resp = await _runtime_request(
        "GET",
        runtime_host,
        project_token,
        auth_token,
        "/file",
        params={"path": path},
    )
    resp.raise_for_status()
    payload = _parse_json(resp)
    return _unwrap_data(payload)


async def get_file_content(
    runtime_host: str,
    project_token: str,
    auth_token: str,
    path: str,
) -> bytes:
    resp = await _runtime_request(
        "GET",
        runtime_host,
        project_token,
        auth_token,
        "/file/content",
        params={"path": path},
    )
    resp.raise_for_status()
    return bytes(resp.content)


async def get_file_status(runtime_host: str, project_token: str, auth_token: str) -> Any:
    resp = await _runtime_request(
        "GET",
        runtime_host,
        project_token,
        auth_token,
        "/file/status",
    )
    resp.raise_for_status()
    payload = _parse_json(resp)
    return _unwrap_data(payload)


async def get_health(runtime_host: str) -> Any:
    resp = await _retry_request("GET", f"{_runtime_base(runtime_host)}/health")
    resp.raise_for_status()
    return _parse_json(resp)


async def request_preview(
    runtime_host: str,
    project_token: str,
    auth_token: str,
    port: int = 8080,
) -> Any:
    resp = await _runtime_request(
        "POST",
        runtime_host,
        project_token,
        auth_token,
        "/preview",
        json={"port": port},
    )
    resp.raise_for_status()
    payload = _parse_json(resp)
    return _unwrap_data(payload)
