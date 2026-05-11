"""
Cross-account boundary probe for NodeOps/CreateOS runtime.

Goal:
1) A creates deployment/session.
2) Use B auth token against A deployment/session.
3) Verify which operations are accepted/rejected.
4) Snapshot A/B credit amount before and after.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from backend.services import nodeops_client as noc
from backend.storage.file_store import accounts_path, read_json


def _pick_accounts() -> tuple[dict[str, Any], dict[str, Any]]:
    raw = read_json(accounts_path())
    if not isinstance(raw, list):
        raise RuntimeError("accounts.json is invalid")
    candidates = [
        a for a in raw
        if isinstance(a, dict)
        and str(a.get("auth_token") or "").strip()
        and str(a.get("status") or "").strip().lower() == "available"
    ]
    if len(candidates) < 2:
        raise RuntimeError("Need at least 2 available accounts with auth_token")
    # Keep deterministic selection for reproducibility.
    return candidates[0], candidates[1]


def _runtime_base(runtime_host_or_url: str) -> str:
    value = str(runtime_host_or_url or "").strip().rstrip("/")
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return f"https://{value}"


def _as_dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _pick_runtime_host(detail: dict[str, Any]) -> str:
    host = (
        detail.get("runtimeHost")
        or detail.get("runtime_host")
        or detail.get("server_endpoint")
        or detail.get("endpoint")
        or detail.get("host")
        or ""
    )
    host = str(host).strip().rstrip("/")
    if host.startswith("https://"):
        host = host[len("https://"):]
    elif host.startswith("http://"):
        host = host[len("http://"):]
    return host


def _pick_project_token(detail: dict[str, Any]) -> str:
    token = detail.get("projectToken") or detail.get("project_token") or detail.get("token") or ""
    return str(token).strip()


def _pick_deployment_id(detail: dict[str, Any]) -> str:
    dep_id = detail.get("id") or detail.get("deploymentId") or detail.get("deployment_id") or ""
    return str(dep_id).strip()


def _pick_session_id(payload: Any) -> str:
    data = _as_dict(payload)
    if not data and isinstance(payload, dict):
        data = _as_dict(payload.get("data"))
    sid = str(
        data.get("id")
        or data.get("sessionId")
        or data.get("session_id")
        or ""
    ).strip()
    return sid


def _extract_credit_amount(payload: Any) -> float | None:
    try:
        data = _as_dict(payload).get("data")
        if isinstance(data, dict):
            amt = data.get("amount")
            if isinstance(amt, (int, float)):
                return float(amt)
            if isinstance(amt, str) and amt.strip():
                return float(amt.strip())
    except Exception:
        return None
    return None


def _short(s: str, n: int = 10) -> str:
    s = str(s or "")
    return s if len(s) <= n else f"{s[:n]}..."


def _resp_brief_json(resp_text: str) -> str:
    try:
        obj = json.loads(resp_text)
        raw = json.dumps(obj, ensure_ascii=False)
    except Exception:
        raw = str(resp_text or "")
    raw = raw.strip().replace("\n", " ")
    return raw if len(raw) <= 240 else f"{raw[:240]}..."


async def _runtime_request(
    method: str,
    runtime_host: str,
    project_token: str,
    ygg_token: str,
    path: str,
    **kwargs,
):
    headers = {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "x-project-token": project_token,
        "y-gg-token": ygg_token,
    }
    url = f"{_runtime_base(runtime_host)}{path}"
    client = noc.get_client()
    return await client.request(method, url, headers=headers, **kwargs)


async def _build_deployment_for_account(account: dict[str, Any]) -> tuple[str, str, str]:
    prompt = f"cross-boundary-{uuid.uuid4().hex[:8]}"
    created = await noc.create_deployment(account["auth_token"], prompt=prompt)
    detail = _as_dict(created.get("data")) if isinstance(created, dict) else {}
    detail = detail or _as_dict(created)

    dep_id = _pick_deployment_id(detail)
    runtime_host = _pick_runtime_host(detail)
    project_token = _pick_project_token(detail)

    if runtime_host and project_token:
        return dep_id, runtime_host, project_token

    if not dep_id:
        raise RuntimeError(f"create_deployment missing deployment id: {created}")

    # fallback polling
    last_err = ""
    for _ in range(20):
        d = await noc.get_deployment(account["auth_token"], dep_id)
        dd = _as_dict(d.get("data")) if isinstance(d, dict) else {}
        dd = dd or _as_dict(d)
        runtime_host = _pick_runtime_host(dd)
        project_token = _pick_project_token(dd)
        if runtime_host and project_token:
            return dep_id, runtime_host, project_token
        last_err = str(d)[:200]
        await asyncio.sleep(2)
    raise RuntimeError(f"deployment not ready: {dep_id} {last_err}")


async def _create_session_with_retry(runtime_host: str, project_token: str, auth_token: str) -> str:
    last_exc: Exception | None = None
    for _ in range(6):
        try:
            created = await noc.create_session(
                runtime_host,
                project_token,
                auth_token,
                title=f"cross-boundary-session-{uuid.uuid4().hex[:6]}",
            )
            sid = _pick_session_id(created)
            if sid:
                return sid
            last_exc = RuntimeError(f"session id missing: {created}")
        except Exception as exc:  # noqa: PERF203
            last_exc = exc
        await asyncio.sleep(2)
    raise RuntimeError(f"create_session failed: {last_exc}")


async def main():
    acc_a, acc_b = _pick_accounts()

    print("=== Cross-account boundary probe ===")
    print(f"A: {acc_a.get('email')}  ({acc_a.get('id')})")
    print(f"B: {acc_b.get('email')}  ({acc_b.get('id')})")

    credits_a_before = _extract_credit_amount(await noc.get_credits(acc_a["auth_token"]))
    credits_b_before = _extract_credit_amount(await noc.get_credits(acc_b["auth_token"]))
    print(f"credits before  A={credits_a_before}  B={credits_b_before}")

    dep_id, runtime_host, project_token = await _build_deployment_for_account(acc_a)
    print(f"deployment(A)   id={dep_id}  host={runtime_host}")
    print(f"project_token(A) {_short(project_token, 24)}")

    session_id = await _create_session_with_retry(runtime_host, project_token, acc_a["auth_token"])
    print(f"session(A)      id={session_id}")

    probe_id = uuid.uuid4().hex[:8]
    msg_payload = {"parts": [{"type": "text", "text": f"cross-test-{probe_id}"}]}

    # Control: A auth on A deployment/session
    resp_control = await _runtime_request(
        "POST",
        runtime_host,
        project_token,
        acc_a["auth_token"],
        f"/session/{session_id}/message",
        json=msg_payload,
        timeout=30.0,
    )
    print(
        f"[control] A->A session/message   status={resp_control.status_code} "
        f"body={_resp_brief_json(resp_control.text)}"
    )

    # Test 1: B auth on A session/message
    resp_cross_send = await _runtime_request(
        "POST",
        runtime_host,
        project_token,
        acc_b["auth_token"],
        f"/session/{session_id}/message",
        json={"parts": [{"type": "text", "text": f'cross-B-send-{probe_id}'}]},
        timeout=30.0,
    )
    print(
        f"[T1] B->A session/message        status={resp_cross_send.status_code} "
        f"body={_resp_brief_json(resp_cross_send.text)}"
    )

    # Test 2a: B auth reads A file tree
    resp_tree = await _runtime_request(
        "GET",
        runtime_host,
        project_token,
        acc_b["auth_token"],
        "/file",
        params={"path": ""},
        timeout=30.0,
    )
    print(
        f"[T2a] B->A file tree             status={resp_tree.status_code} "
        f"body={_resp_brief_json(resp_tree.text)}"
    )

    # Test 2b: B auth creates a NEW session on A deployment
    resp_cross_create_session = await _runtime_request(
        "POST",
        runtime_host,
        project_token,
        acc_b["auth_token"],
        "/session",
        json={"title": f"cross-create-{probe_id}"},
        timeout=30.0,
    )
    print(
        f"[T2b] B->A create session        status={resp_cross_create_session.status_code} "
        f"body={_resp_brief_json(resp_cross_create_session.text)}"
    )

    cross_session_id = ""
    if resp_cross_create_session.status_code < 300:
        try:
            cross_payload = resp_cross_create_session.json()
        except Exception:
            cross_payload = {}
        cross_session_id = _pick_session_id(cross_payload)
        if cross_session_id:
            resp_cross_send2 = await _runtime_request(
                "POST",
                runtime_host,
                project_token,
                acc_b["auth_token"],
                f"/session/{cross_session_id}/message",
                json={"parts": [{"type": "text", "text": f"cross-B-new-session-{probe_id}"}]},
                timeout=30.0,
            )
            print(
                f"[T2c] B->A(new session) msg    status={resp_cross_send2.status_code} "
                f"body={_resp_brief_json(resp_cross_send2.text)}"
            )
        else:
            print("[T2c] skipped: cross-created session id missing")
    else:
        print("[T2c] skipped: cross-create-session not successful")

    # Give credit ledger a moment.
    await asyncio.sleep(4)
    credits_a_after = _extract_credit_amount(await noc.get_credits(acc_a["auth_token"]))
    credits_b_after = _extract_credit_amount(await noc.get_credits(acc_b["auth_token"]))
    print(f"credits after   A={credits_a_after}  B={credits_b_after}")
    if credits_a_before is not None and credits_a_after is not None:
        print(f"delta A = {credits_a_after - credits_a_before:.6f}")
    if credits_b_before is not None and credits_b_after is not None:
        print(f"delta B = {credits_b_after - credits_b_before:.6f}")

    print("=== done ===")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        try:
            asyncio.run(noc.close_client())
        except Exception:
            pass
