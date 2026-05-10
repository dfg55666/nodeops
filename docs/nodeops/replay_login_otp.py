"""
Replay NodeOps CreateOS OTP login and bootstrap runtime credentials.

Modes:
1) Manual single account:
   python auth/nodeops/replay_login_otp.py --email you@example.com --otp 123456

2) Auto single account (mail.tm):
   python auth/nodeops/replay_login_otp.py --source mailtm

3) Auto single account (QQ IMAP):
   python auth/nodeops/replay_login_otp.py --source qq

4) Batch concurrent:
   python auth/nodeops/replay_login_otp.py --source both --count 5 --threads 3
   In batch mode with both sources enabled, each attempt randomly chooses source.

5) QQ bulk prefetch (high-throughput):
   python auth/nodeops/replay_login_otp.py --auto-qq --qq-bulk-prefetch --count 10 --threads 10
   Flow: generate N aliases -> send OTP concurrently -> fetch all codes once from QQ -> verify concurrently.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
AUTH_DIR = SCRIPT_DIR.parent
if str(AUTH_DIR) not in os.sys.path:
    os.sys.path.insert(0, str(AUTH_DIR))

from mailtm_inbox import (
    HotmailOAuthInbox,
    MailTMInbox,
    QQIMAPInbox,
    load_hotmail_oauth_cards_from_zhanghaoya,
    load_outlook_accounts,
    load_zhanghaoya_key,
)

LOGIN_URL = "https://oneclick-backend.nodeops.xyz/api/v1/login"
VERIFY_URL = "https://oneclick-backend.nodeops.xyz/api/v1/login/verify"
DEPLOYMENT_URL = "https://stage-vibe-coder-api.nodeops.xyz/api/v1/deployments"
USAGE_URL = "https://stage-vibe-coder-api.nodeops.xyz/api/v1/usage"
CREATEOS_API_BASE = "https://api-createos.nodeops.network/v1"
SKUS_CREDIT_URL = f"{CREATEOS_API_BASE}/skus/credit"
CREDIT_CONVERSION_URL = f"{CREATEOS_API_BASE}/payments/credit-conversion-rate"
CREDITS_OPENROUTER_URL = f"{CREATEOS_API_BASE}/credits/openrouter"
DEFAULT_CREDIT_SKU_ID = "00000000-0000-0000-0000-000000000007"
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

_print_lock = threading.Lock()
_verified_log_lock = threading.Lock()
_verified_jsonl_path = ""


def _safe_print(*parts: object) -> None:
    with _print_lock:
        print(*parts)


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return bool(default)
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _default_output_path() -> str:
    script_dir = Path(__file__).resolve().parent
    return str(script_dir / "nodeops_auth_token.json")


def _default_batch_output_dir() -> str:
    script_dir = Path(__file__).resolve().parent
    return str(script_dir / "tokens")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: str, payload: Dict[str, Any], announce: bool = True) -> str:
    out = Path(path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if announce:
        _safe_print(f"saved json: {out}")
    return str(out)


def _append_jsonl(path: str, payload: Dict[str, Any]) -> None:
    if not path:
        return
    try:
        out = Path(path).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False)
        with _verified_log_lock:
            with out.open("a", encoding="utf-8") as fp:
                fp.write(line + "\n")
    except Exception:
        # Best-effort archival; never break the registration flow.
        return


def _parse_source_mode(source_mode: str) -> List[str]:
    mode = str(source_mode or "").strip().lower()
    if mode == "":
        return []
    if mode == "mailtm":
        return ["mailtm"]
    if mode == "qq":
        return ["qq"]
    if mode == "outlook":
        return ["outlook"]
    if mode == "both":
        return ["mailtm", "qq"]
    if mode == "all":
        return ["mailtm", "qq", "outlook"]
    raise SystemExit(f"Unsupported --source value: {source_mode} (allowed: mailtm|qq|outlook|both|all)")


def _dedupe_sources(sources: List[str]) -> List[str]:
    out: List[str] = []
    for source in sources:
        s = str(source or "").strip().lower()
        if not s or s in out:
            continue
        out.append(s)
    return out


def _mask_token(token: str) -> str:
    token = token.strip()
    if len(token) <= 16:
        return token
    return f"{token[:8]}...{token[-8:]}"


def _headers() -> Dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Referer": "https://createos.nodeops.network/",
        "ReferralURL": "https://nodeops.network",
    }


def _parse_json_or_text(resp: requests.Response) -> Dict[str, Any]:
    try:
        parsed = resp.json()
        if isinstance(parsed, dict):
            return parsed
        return {"raw": parsed}
    except Exception:
        return {"raw_text": resp.text[:2000]}


def _redeem_openrouter_credits(
    x_auth_token: str,
    headers: Dict[str, str],
    timeout_s: int,
    log_prefix: str,
    nodeops_credits: int,
    chunk_nodeops_credits: int,
) -> Dict[str, Any]:
    chunk = int(chunk_nodeops_credits)
    if chunk not in (100, 250):
        chunk = 100
    requested = int(max(0, nodeops_credits))
    requested_openrouter = round(requested / 100.0, 4)
    _safe_print(
        f"{log_prefix} redeem start nodeops_credits={requested} chunk={chunk} "
        f"(openrouter={requested_openrouter})"
    )
    result: Dict[str, Any] = {
        "credits_redeem_attempted": True,
        "credits_redeem_credits": requested,
        "credits_redeem_chunk_nodeops_credits": chunk,
        "credits_redeem_requested_openrouter_credits": requested_openrouter,
        "credits_redeem_success": False,
    }

    common_headers = {
        "Accept": "application/json, text/plain, */*",
        "X-Auth-Token": x_auth_token,
    }
    post_headers = {
        **common_headers,
        "Content-Type": "application/json",
        "ReferralURL": str(headers.get("ReferralURL", "https://nodeops.network")),
    }

    try:
        def _redeem_call(openrouter_credits: float) -> Dict[str, Any]:
            resp = requests.post(
                CREDITS_OPENROUTER_URL,
                headers=post_headers,
                json={"credits": openrouter_credits},
                timeout=timeout_s,
            )
            payload = _parse_json_or_text(resp)
            ok = (
                resp.status_code < 400
                and str(payload.get("status") or "").strip().lower() == "success"
            )
            return {
                "status_code": int(resp.status_code),
                "payload": payload,
                "ok": bool(ok),
                "error": str(
                    payload.get("data")
                    or payload.get("message")
                    or payload.get("raw_text")
                    or resp.text[:500]
                ),
            }

        def _build_fallback_plan(target_nodeops: int, preferred_chunk: int) -> List[int]:
            # Use a mixed 100/250 plan to maximize redeemable credits <= target.
            best_total = 0
            best_250 = 0
            best_100 = 0
            for n250 in range(target_nodeops // 250, -1, -1):
                remaining = target_nodeops - (n250 * 250)
                n100 = remaining // 100
                total = (n250 * 250) + (n100 * 100)
                if total > best_total:
                    best_total = total
                    best_250 = n250
                    best_100 = n100
                    continue
                if total != best_total:
                    continue
                if preferred_chunk == 250 and n250 > best_250:
                    best_250 = n250
                    best_100 = n100
                elif preferred_chunk == 100 and n100 > best_100:
                    best_250 = n250
                    best_100 = n100
            if best_total <= 0:
                return []
            if preferred_chunk == 250:
                return [250] * best_250 + [100] * best_100
            return [100] * best_100 + [250] * best_250

        credits_resp = requests.get(f"{CREATEOS_API_BASE}/credits", headers=common_headers, timeout=timeout_s)
        result["credits_redeem_balance_status_code"] = int(credits_resp.status_code)
        credits_payload = _parse_json_or_text(credits_resp)
        result["credits_redeem_balance_response"] = credits_payload
        available_nodeops = 0.0
        data = credits_payload.get("data")
        if isinstance(data, dict):
            try:
                available_nodeops = float(data.get("amount") or 0)
            except (TypeError, ValueError):
                available_nodeops = 0.0
        result["credits_redeem_available_nodeops_credits"] = available_nodeops

        sku_resp = requests.get(SKUS_CREDIT_URL, headers=common_headers, timeout=timeout_s)
        result["credits_redeem_sku_status_code"] = int(sku_resp.status_code)
        sku_payload = _parse_json_or_text(sku_resp)
        result["credits_redeem_sku_response"] = sku_payload

        sku_id = DEFAULT_CREDIT_SKU_ID
        if sku_resp.status_code < 400:
            data = sku_payload.get("data")
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    sku = item.get("sku")
                    if isinstance(sku, dict):
                        candidate = str(sku.get("id") or "").strip()
                        if candidate:
                            sku_id = candidate
                            break

        requested_nodeops = int(max(0, requested))
        if requested_nodeops == 0:
            result["credits_redeem_error"] = "requested credits is zero"
            return result

        target_nodeops = min(requested_nodeops, int(max(0.0, available_nodeops)))
        result["credits_redeem_requested_nodeops_credits"] = requested_nodeops
        target_openrouter = round(target_nodeops / 100.0, 4)
        result["credits_redeem_target_nodeops_credits"] = target_nodeops
        result["credits_redeem_target_openrouter_credits"] = target_openrouter

        if target_nodeops <= 0:
            result["credits_redeem_error"] = (
                f"insufficient balance: available={available_nodeops}, requested={requested_nodeops}"
            )
            return result

        # API uses openrouter credits: 1.0 means 100 NodeOps credits.
        conversion_resp = requests.get(
            CREDIT_CONVERSION_URL,
            headers=common_headers,
            params={
                "skuId": sku_id,
                "creditMultiplier": 1,
                "amount": target_openrouter,
                "paymentMethod": "checkout",
            },
            timeout=timeout_s,
        )
        result["credits_redeem_conversion_status_code"] = int(conversion_resp.status_code)
        result["credits_redeem_conversion_response"] = _parse_json_or_text(conversion_resp)

        step_results: List[Dict[str, Any]] = []
        redeemed_nodeops = 0
        redeemed_openrouter = 0.0
        last_step_payload: Dict[str, Any] = {}
        last_status_code = 0

        result["credits_redeem_strategy"] = "one_shot"
        result["credits_redeem_one_shot_attempted"] = True
        one_shot = _redeem_call(target_openrouter)
        result["credits_redeem_one_shot_status_code"] = one_shot["status_code"]
        result["credits_redeem_one_shot_response"] = one_shot["payload"]
        result["credits_redeem_one_shot_ok"] = one_shot["ok"]
        last_status_code = int(one_shot["status_code"])
        if isinstance(one_shot["payload"], dict):
            last_step_payload = one_shot["payload"]

        if one_shot["ok"]:
            redeemed_nodeops = target_nodeops
            redeemed_openrouter = target_openrouter
            step_results.append(
                {
                    "step": 1,
                    "mode": "one_shot",
                    "request_openrouter_credits": target_openrouter,
                    "request_nodeops_credits": target_nodeops,
                    "status_code": int(one_shot["status_code"]),
                    "ok": True,
                    "response": one_shot["payload"],
                }
            )
            result["credits_redeem_planned_nodeops_credits"] = target_nodeops
            result["credits_redeem_planned_steps"] = 1
            result["credits_redeem_openrouter_per_step"] = target_openrouter
        else:
            result["credits_redeem_one_shot_error"] = one_shot["error"]
            result["credits_redeem_strategy"] = "fallback_chunks"
            fallback_plan = _build_fallback_plan(target_nodeops, chunk)
            result["credits_redeem_fallback_chunks"] = fallback_plan
            result["credits_redeem_planned_nodeops_credits"] = int(sum(fallback_plan))
            result["credits_redeem_planned_steps"] = len(fallback_plan)
            if fallback_plan:
                result["credits_redeem_openrouter_per_step"] = round(fallback_plan[0] / 100.0, 4)
            else:
                result["credits_redeem_openrouter_per_step"] = round(chunk / 100.0, 4)

            if not fallback_plan:
                result["credits_redeem_error"] = str(
                    result.get("credits_redeem_one_shot_error")
                    or f"fallback plan empty for target_nodeops={target_nodeops}"
                )
            else:
                _safe_print(
                    f"{log_prefix} redeem one-shot failed, fallback to chunks: {fallback_plan}"
                )
                for step_idx, nodeops_chunk in enumerate(fallback_plan, start=1):
                    openrouter_chunk = round(nodeops_chunk / 100.0, 4)
                    chunk_step = _redeem_call(openrouter_chunk)
                    last_status_code = int(chunk_step["status_code"])
                    if isinstance(chunk_step["payload"], dict):
                        last_step_payload = chunk_step["payload"]
                    step_result = {
                        "step": step_idx,
                        "mode": "fallback_chunk",
                        "request_openrouter_credits": openrouter_chunk,
                        "request_nodeops_credits": int(nodeops_chunk),
                        "status_code": int(chunk_step["status_code"]),
                        "ok": bool(chunk_step["ok"]),
                        "response": chunk_step["payload"],
                    }
                    step_results.append(step_result)
                    if not chunk_step["ok"]:
                        result["credits_redeem_error"] = chunk_step["error"]
                        break
                    redeemed_nodeops += int(nodeops_chunk)
                    redeemed_openrouter = round(redeemed_openrouter + openrouter_chunk, 4)

        result["credits_redeem_steps"] = step_results
        result["credits_redeem_status_code"] = int(last_status_code)
        result["credits_redeem_response"] = last_step_payload
        result["credits_redeem_redeemed_nodeops_credits"] = redeemed_nodeops
        result["credits_redeem_redeemed_openrouter_credits"] = redeemed_openrouter
        result["credits_redeem_success"] = bool(redeemed_nodeops >= target_nodeops)
        result["credits_redeem_partial_success"] = bool(redeemed_nodeops > 0)
        if not result["credits_redeem_success"] and "credits_redeem_error" not in result:
            result["credits_redeem_error"] = (
                f"redeemed {redeemed_nodeops}/{target_nodeops} nodeops credits (requested={requested_nodeops})"
            )

        usage_headers = dict(common_headers)
        usage_headers["ReferralURL"] = str(headers.get("ReferralURL", "https://nodeops.network"))
        usage_resp = requests.get(USAGE_URL, headers=usage_headers, timeout=timeout_s)
        result["credits_redeem_usage_status_code"] = int(usage_resp.status_code)
        result["usage_after_redeem"] = _parse_json_or_text(usage_resp)
        return result
    except Exception as exc:
        result["credits_redeem_error"] = str(exc)
        return result


def _finalize_pending_redeem(
    payload: Dict[str, Any],
    headers: Dict[str, str],
    timeout_s: int,
    log_prefix: str,
    runtime_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    if not bool(payload.get("credits_redeem_pending")):
        return payload

    source = str(payload.get("source") or "").strip().lower()
    if source == "manual":
        payload["credits_redeem_pending"] = False
        return payload

    token = str(payload.get("x_auth_token") or "").strip()
    if not token:
        payload["credits_redeem_pending"] = False
        payload["credits_redeem_success"] = False
        payload["credits_redeem_error"] = "missing x_auth_token"
        return payload

    redeem_amount = int(max(0, int(runtime_cfg.get("redeem_credits_amount", 0) or 0)))
    redeem_chunk = int(runtime_cfg.get("redeem_chunk_nodeops_credits", 100) or 100)
    redeem_strict = bool(runtime_cfg.get("redeem_credits_strict"))

    redeem_result = _redeem_openrouter_credits(
        x_auth_token=token,
        headers=headers,
        timeout_s=timeout_s,
        log_prefix=log_prefix,
        nodeops_credits=redeem_amount,
        chunk_nodeops_credits=redeem_chunk,
    )
    payload.update(redeem_result)
    payload["credits_redeem_pending"] = False
    payload["credits_redeem_async"] = bool(runtime_cfg.get("redeem_async"))
    _safe_print(
        f"{log_prefix} redeem credits={redeem_amount} "
        f"status={redeem_result.get('credits_redeem_status_code')} "
        f"success={redeem_result.get('credits_redeem_success')}"
    )
    if redeem_strict and not bool(redeem_result.get("credits_redeem_success")):
        raise RuntimeError(
            "credit redeem failed: "
            + str(redeem_result.get("credits_redeem_error") or redeem_result.get("credits_redeem_response"))
        )
    return payload


def _send_otp(email: str, headers: Dict[str, str], timeout_s: int, log_prefix: str) -> None:
    body = {"email": email, "from": "createos"}
    resp = requests.post(LOGIN_URL, headers=headers, json=body, timeout=timeout_s)
    _safe_print(f"{log_prefix} login status:", resp.status_code)
    _safe_print(f"{log_prefix} login body:", resp.text)
    resp.raise_for_status()


def _verify_otp(email: str, otp: str, headers: Dict[str, str], timeout_s: int, log_prefix: str) -> Dict[str, Any]:
    body: Dict[str, Any] = {"email": email, "otp": otp}
    resp = requests.post(VERIFY_URL, headers=headers, json=body, timeout=timeout_s)
    _safe_print(f"{log_prefix} verify status:", resp.status_code)
    if resp.status_code >= 400:
        raise RuntimeError(f"verify failed status={resp.status_code}, body={resp.text[:500]}")
    return resp.json()


def _build_token_payload(email: str, verify_data: Dict[str, Any], source: str) -> Dict[str, Any]:
    token = str((verify_data.get("data") or {}).get("token") or "").strip()
    if not token:
        raise RuntimeError("verify succeeded but no data.token returned")
    payload = {
        "created_at": _utc_now_iso(),
        "source": source,
        "email": email,
        "uuid": (verify_data.get("data") or {}).get("uuid"),
        "x_auth_token": token,
        "is_new_user": (verify_data.get("data") or {}).get("is_new_user"),
        "is_wallet_registered": (verify_data.get("data") or {}).get("is_wallet_registered"),
        "verify_response": verify_data,
    }
    # Archive as soon as OTP verification succeeds, so tokens are not lost even if
    # runtime bootstrap or import later fails.
    if _verified_jsonl_path:
        _append_jsonl(_verified_jsonl_path, payload)
    return payload


def _create_deployment(
    x_auth_token: str,
    headers: Dict[str, str],
    timeout_s: int,
    log_prefix: str,
    deployment_prompt: str,
) -> Dict[str, Any]:
    deploy_headers = dict(headers)
    deploy_headers["X-Auth-Token"] = x_auth_token

    body = {"prompt": deployment_prompt}
    resp = requests.post(DEPLOYMENT_URL, headers=deploy_headers, json=body, timeout=timeout_s)
    _safe_print(f"{log_prefix} deployment status:", resp.status_code)
    if resp.status_code >= 400:
        raise RuntimeError(f"deployment failed status={resp.status_code}, body={resp.text[:500]}")

    raw_text = resp.text
    payload = resp.json()
    if not isinstance(payload, dict):
        raise RuntimeError("deployment response is not a JSON object")
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        raise RuntimeError("deployment response missing data object")

    deployment_id = str(data.get("id") or "").strip()
    server_endpoint = str(data.get("server_endpoint") or "").strip().rstrip("/")
    project_token = str(data.get("token") or "").strip()

    # NodeOps may return 202 + {data:{message,status,request_id}} when resources are busy.
    # We treat that as "queued" instead of hard-failing, so we can persist the account
    # credentials and retry runtime bootstrap later.
    if not deployment_id:
        request_id = str(data.get("request_id") or data.get("requestId") or "").strip()
        queue_status = str(data.get("status") or "").strip()
        queue_message = str(data.get("message") or "").strip()
        if request_id:
            return {
                "deployment_queued": True,
                "deployment_request_id": request_id,
                "deployment_queue_status": queue_status,
                "deployment_queue_message": queue_message,
                "deployment_status_code": int(resp.status_code),
                "deployment_response_raw": raw_text,
                "deployment_response": payload,
            }

    if not deployment_id:
        raise RuntimeError("deployment succeeded but no data.id returned")
    if not server_endpoint:
        raise RuntimeError("deployment succeeded but no data.server_endpoint returned")
    if not project_token:
        raise RuntimeError("deployment succeeded but no data.token returned")

    return {
        "deployment_id": deployment_id,
        "server_endpoint": server_endpoint,
        "x_project_token": project_token,
        "deployment_request_id": "",
        "deployment_queue_status": "",
        "deployment_queue_message": "",
        "deployment_status_code": int(resp.status_code),
        "deployment_response_raw": raw_text,
        "deployment_response": payload,
    }


def _create_session(
    server_endpoint: str,
    x_project_token: str,
    headers: Dict[str, str],
    timeout_s: int,
    log_prefix: str,
    empty_raw_body: bool,
) -> Dict[str, Any]:
    session_headers = dict(headers)
    session_headers["x-project-token"] = x_project_token

    session_url = f"{server_endpoint.rstrip('/')}/session"
    if empty_raw_body:
        resp = requests.post(session_url, headers=session_headers, data=b"", timeout=timeout_s)
    else:
        resp = requests.post(session_url, headers=session_headers, json={}, timeout=timeout_s)
    _safe_print(f"{log_prefix} session status:", resp.status_code)
    if resp.status_code >= 400:
        raise RuntimeError(f"create session failed status={resp.status_code}, body={resp.text[:500]}")

    payload = resp.json()
    if not isinstance(payload, dict):
        raise RuntimeError("session response is not a JSON object")
    session_id = str(payload.get("id") or "").strip()
    if not session_id:
        raise RuntimeError("create session succeeded but no id returned")

    return {
        "session_id": session_id,
        "session_response": payload,
    }


def _bootstrap_runtime(
    x_auth_token: str,
    headers: Dict[str, str],
    timeout_s: int,
    log_prefix: str,
    runtime_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    deployment = _create_deployment(
        x_auth_token=x_auth_token,
        headers=headers,
        timeout_s=timeout_s,
        log_prefix=log_prefix,
        deployment_prompt=str(runtime_cfg["deployment_prompt"]),
    )
    if bool(deployment.get("deployment_queued")):
        _safe_print(
            f"{log_prefix} deployment queued request_id={deployment.get('deployment_request_id')}"
        )
        return {
            "runtime_ready": False,
            "deployment_id": "",
            "server_endpoint": "",
            "x_project_token": "",
            "session_id": "",
            "deployment_request_id": deployment.get("deployment_request_id"),
            "deployment_queue_status": deployment.get("deployment_queue_status"),
            "deployment_queue_message": deployment.get("deployment_queue_message"),
            "deployment_status_code": deployment.get("deployment_status_code"),
            "deployment_response_raw": deployment.get("deployment_response_raw"),
            "deployment_response": deployment.get("deployment_response"),
            "session_response": {},
        }

    _safe_print(f"{log_prefix} deployment={deployment['deployment_id']}")
    _safe_print(f"{log_prefix} project_token={_mask_token(str(deployment['x_project_token']))}")

    session = _create_session(
        server_endpoint=str(deployment["server_endpoint"]),
        x_project_token=str(deployment["x_project_token"]),
        headers=headers,
        timeout_s=timeout_s,
        log_prefix=log_prefix,
        empty_raw_body=bool(runtime_cfg["session_empty_raw_body"]),
    )
    _safe_print(f"{log_prefix} session={session['session_id']}")

    return {
        "runtime_ready": True,
        "deployment_id": deployment["deployment_id"],
        "server_endpoint": deployment["server_endpoint"],
        "x_project_token": deployment["x_project_token"],
        "session_id": session["session_id"],
        "deployment_request_id": deployment.get("deployment_request_id") or "",
        "deployment_queue_status": deployment.get("deployment_queue_status") or "",
        "deployment_queue_message": deployment.get("deployment_queue_message") or "",
        "deployment_status_code": deployment.get("deployment_status_code"),
        "deployment_response_raw": deployment.get("deployment_response_raw"),
        "deployment_response": deployment["deployment_response"],
        "session_response": session["session_response"],
    }


def _build_account_payload(
    email: str,
    verify_data: Dict[str, Any],
    source: str,
    headers: Dict[str, str],
    timeout_s: int,
    log_prefix: str,
    runtime_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    payload = _build_token_payload(email=email, verify_data=verify_data, source=source)

    redeem_enabled = bool(runtime_cfg.get("redeem_credits_enabled"))
    redeem_amount = int(max(0, int(runtime_cfg.get("redeem_credits_amount", 0) or 0)))
    redeem_chunk = int(max(100, int(runtime_cfg.get("redeem_chunk_nodeops_credits", 100) or 100)))
    redeem_async = bool(runtime_cfg.get("redeem_async"))
    if source != "manual" and redeem_enabled and redeem_amount > 0:
        if redeem_async:
            payload.update(
                {
                    "credits_redeem_pending": True,
                    "credits_redeem_async": True,
                    "credits_redeem_credits": redeem_amount,
                    "credits_redeem_chunk_nodeops_credits": redeem_chunk,
                }
            )
        else:
            payload["credits_redeem_pending"] = True
            _finalize_pending_redeem(
                payload=payload,
                headers=headers,
                timeout_s=timeout_s,
                log_prefix=log_prefix,
                runtime_cfg=runtime_cfg,
            )

    if bool(runtime_cfg["create_runtime"]):
        try:
            runtime_payload = _bootstrap_runtime(
                x_auth_token=str(payload["x_auth_token"]),
                headers=headers,
                timeout_s=timeout_s,
                log_prefix=log_prefix,
                runtime_cfg=runtime_cfg,
            )
            payload.update(runtime_payload)
        except Exception as exc:
            # Runtime bootstrap can fail even though X-Auth-Token is valid.
            # Do NOT throw away the token; persist it for later recovery.
            payload.update(
                {
                    "runtime_ready": False,
                    "runtime_error": str(exc),
                }
            )
    return payload


def _run_source_mailtm(
    task_prefix: str,
    timeout_s: int,
    headers: Dict[str, str],
    runtime_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    inbox = MailTMInbox(logger=lambda msg, p=task_prefix: _safe_print(f"{p} {msg}"))
    email = inbox.generate_email()
    _safe_print(f"{task_prefix} source=mailtm email={email}")
    _send_otp(email=email, headers=headers, timeout_s=30, log_prefix=task_prefix)
    otp = inbox.wait_for_verification_code(timeout_s=timeout_s, debug=True)
    _safe_print(f"{task_prefix} source=mailtm otp={otp}")
    verify_data = _verify_otp(email=email, otp=otp, headers=headers, timeout_s=30, log_prefix=task_prefix)
    payload = _build_account_payload(
        email=email,
        verify_data=verify_data,
        source="mailtm",
        headers=headers,
        timeout_s=timeout_s,
        log_prefix=task_prefix,
        runtime_cfg=runtime_cfg,
    )
    _safe_print(f"{task_prefix} source=mailtm token={_mask_token(payload['x_auth_token'])}")
    return payload


def _run_source_qq(
    task_prefix: str,
    timeout_s: int,
    headers: Dict[str, str],
    qq_cfg: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    inbox = QQIMAPInbox(
        qq_email=qq_cfg["qq_email"],
        qq_password=qq_cfg["qq_password"],
        qq_imap_server=qq_cfg["qq_imap_server"],
        qq_imap_port=int(qq_cfg["qq_imap_port"]),
        folder=qq_cfg["qq_folder"],
        alias_domain=qq_cfg["alias_domain"],
        logger=lambda msg, p=task_prefix: _safe_print(f"{p} {msg}"),
    )
    email = inbox.generate_email(prefix_len=int(qq_cfg["alias_prefix_len"]))
    _safe_print(f"{task_prefix} source=qq email={email}")
    _send_otp(email=email, headers=headers, timeout_s=30, log_prefix=task_prefix)
    otp = inbox.wait_for_verification_code(
        timeout_s=timeout_s,
        debug=True,
        recipient=email,
        poll_interval_s=float(qq_cfg["qq_poll_interval_s"]),
        max_scan_per_poll=int(qq_cfg["qq_max_scan_per_poll"]),
        delete_on_match=bool(qq_cfg["qq_delete_fetched"]),
    )
    _safe_print(f"{task_prefix} source=qq otp={otp}")
    verify_data = _verify_otp(email=email, otp=otp, headers=headers, timeout_s=30, log_prefix=task_prefix)
    payload = _build_account_payload(
        email=email,
        verify_data=verify_data,
        source="qq",
        headers=headers,
        timeout_s=timeout_s,
        log_prefix=task_prefix,
        runtime_cfg=runtime_cfg,
    )
    _safe_print(f"{task_prefix} source=qq token={_mask_token(payload['x_auth_token'])}")
    return payload


def _run_source_outlook(
    task_prefix: str,
    task_id: int,
    timeout_s: int,
    headers: Dict[str, str],
    outlook_cfg: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    cards = outlook_cfg.get("cards") or []
    if not isinstance(cards, list) or not cards:
        raise RuntimeError("outlook source requires preloaded oauth cards")
    idx = max(0, min(len(cards) - 1, int(task_id) - 1))
    card = cards[idx]
    if not isinstance(card, (list, tuple)) or len(card) < 4:
        raise RuntimeError(f"invalid outlook oauth card at index={idx}")

    email = str(card[0] or "").strip()
    client_id = str(card[2] or "").strip()
    refresh_token = str(card[3] or "").strip()
    if not email or not client_id or not refresh_token:
        raise RuntimeError(f"outlook oauth card missing fields at index={idx}")

    inbox = HotmailOAuthInbox(
        email=email,
        client_id=client_id,
        refresh_token=refresh_token,
        folder=str(outlook_cfg.get("folder") or "auto"),
        logger=lambda msg, p=task_prefix: _safe_print(f"{p} {msg}"),
    )
    _safe_print(f"{task_prefix} source=outlook email={email}")
    _send_otp(email=email, headers=headers, timeout_s=30, log_prefix=task_prefix)
    otp = inbox.wait_for_verification_code(
        timeout_s=timeout_s,
        debug=True,
        recipient=email,
        poll_interval_s=float(outlook_cfg.get("poll_interval_s", 4.0)),
        max_scan_per_poll=int(outlook_cfg.get("max_scan_per_poll", 20)),
        delete_on_match=bool(outlook_cfg.get("delete_fetched")),
    )
    _safe_print(f"{task_prefix} source=outlook otp={otp}")
    verify_data = _verify_otp(email=email, otp=otp, headers=headers, timeout_s=30, log_prefix=task_prefix)
    payload = _build_account_payload(
        email=email,
        verify_data=verify_data,
        source="outlook",
        headers=headers,
        timeout_s=timeout_s,
        log_prefix=task_prefix,
        runtime_cfg=runtime_cfg,
    )
    _safe_print(f"{task_prefix} source=outlook token={_mask_token(payload['x_auth_token'])}")
    return payload


def _run_auto_once(
    task_id: int,
    timeout_s: int,
    max_attempts: int,
    headers: Dict[str, str],
    enabled_sources: List[str],
    qq_cfg: Dict[str, Any],
    outlook_cfg: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    prefix = f"[T{task_id}]"
    attempts = max(1, max_attempts)
    rng = random.Random(time_seed := (task_id * 1000003 + int(datetime.now().timestamp())))
    _safe_print(f"{prefix} rng_seed={time_seed}")
    last_error: Optional[Exception] = None

    for attempt in range(1, attempts + 1):
        source = rng.choice(enabled_sources)
        try:
            _safe_print(f"{prefix} attempt={attempt}/{attempts} source={source}")
            if source == "mailtm":
                return _run_source_mailtm(
                    task_prefix=prefix,
                    timeout_s=timeout_s,
                    headers=headers,
                    runtime_cfg=runtime_cfg,
                )
            if source == "qq":
                return _run_source_qq(
                    task_prefix=prefix,
                    timeout_s=timeout_s,
                    headers=headers,
                    qq_cfg=qq_cfg,
                    runtime_cfg=runtime_cfg,
                )
            if source == "outlook":
                return _run_source_outlook(
                    task_prefix=prefix,
                    task_id=task_id,
                    timeout_s=timeout_s,
                    headers=headers,
                    outlook_cfg=outlook_cfg,
                    runtime_cfg=runtime_cfg,
                )
            raise RuntimeError(f"unsupported source: {source}")
        except Exception as exc:
            last_error = exc
            _safe_print(f"{prefix} attempt={attempt} source={source} failed: {exc}")

    raise RuntimeError(f"all attempts failed after {attempts}: {last_error}")


def _run_single_manual(
    email: str,
    otp: str,
    headers: Dict[str, str],
    timeout_s: int,
    runtime_cfg: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    _send_otp(email=email, headers=headers, timeout_s=30, log_prefix="[single]")
    if not otp:
        _safe_print("No OTP provided; stop after sending OTP.")
        return None
    verify_data = _verify_otp(email=email, otp=otp, headers=headers, timeout_s=30, log_prefix="[single]")
    payload = _build_account_payload(
        email=email,
        verify_data=verify_data,
        source="manual",
        headers=headers,
        timeout_s=timeout_s,
        log_prefix="[single]",
        runtime_cfg=runtime_cfg,
    )
    _safe_print("x-auth-token:", _mask_token(payload["x_auth_token"]))
    return payload


def _random_alias(domain: str, prefix_len: int, rng: random.Random) -> str:
    # Keep prefix_len parameter for compatibility; QQ aliases now use
    # human-name + 5 digits to reduce "pure random" patterning.
    _ = prefix_len
    prefix = rng.choice(_HUMAN_NAME_PREFIXES)
    suffix = rng.randint(10000, 99999)
    username = f"{prefix}{suffix}"
    return f"{username}@{domain}"


def _run_batch_qq_prefetch(
    count: int,
    threads: int,
    timeout_s: int,
    output_dir: str,
    summary_output: str,
    output_mode: str,
    headers: Dict[str, str],
    qq_cfg: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
) -> None:
    requested = max(1, count)
    workers = max(1, min(threads, requested))
    mode = str(output_mode or "jsonl").strip().lower()
    if mode not in {"jsonl", "dir"}:
        raise SystemExit(f"Unsupported --output-mode value: {output_mode} (allowed: jsonl|dir)")
    summary_out = Path(summary_output).expanduser().resolve()
    summary_out.parent.mkdir(parents=True, exist_ok=True)
    out_dir = Path(output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    _safe_print(
        f"qq-bulk start: requested={requested}, threads={workers}, "
        f"output_dir={out_dir}, folder={qq_cfg['qq_folder']}"
    )

    rng = random.Random(int(datetime.now().timestamp()))
    emails: List[str] = []
    used = set()
    while len(emails) < requested:
        e = _random_alias(qq_cfg["alias_domain"], int(qq_cfg["alias_prefix_len"]), rng)
        if e in used:
            continue
        used.add(e)
        emails.append(e)

    task_by_email = {email: idx + 1 for idx, email in enumerate(emails)}
    items: List[Dict[str, Any]] = [
        {"task_id": idx + 1, "email": email, "source": "qq_bulk", "ok": False}
        for idx, email in enumerate(emails)
    ]
    item_by_task = {item["task_id"]: item for item in items}

    inbox = QQIMAPInbox(
        qq_email=qq_cfg["qq_email"],
        qq_password=qq_cfg["qq_password"],
        qq_imap_server=qq_cfg["qq_imap_server"],
        qq_imap_port=int(qq_cfg["qq_imap_port"]),
        folder=qq_cfg["qq_folder"],
        alias_domain=qq_cfg["alias_domain"],
        logger=lambda msg: _safe_print(f"[QQ-BULK] {msg}"),
    )
    inbox.reset_start_time()

    # Step 1: send OTP concurrently.
    _safe_print("qq-bulk step1: sending OTP concurrently...")
    send_ok: List[str] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(_send_otp, email, headers, 30, f"[QQ-SEND {task_by_email[email]}]"): email
            for email in emails
        }
        for future in as_completed(future_map):
            email = future_map[future]
            task_id = task_by_email[email]
            item = item_by_task[task_id]
            try:
                future.result()
                send_ok.append(email)
            except Exception as exc:
                item["error"] = f"send_otp_failed: {exc}"
                _safe_print(f"[QQ-SEND {task_id}] failed: {exc}")

    if not send_ok:
        summary = {
            "created_at": _utc_now_iso(),
            "mode": "batch_qq_bulk_prefetch",
            "requested_count": requested,
            "thread_count": workers,
            "success_count": 0,
            "failure_count": requested,
            "output_dir": str(out_dir),
            "items": sorted(items, key=lambda x: int(x["task_id"])),
        }
        _write_json(summary_output, summary, announce=True)
        _safe_print("qq-bulk done: no OTP sent successfully")
        return

    # Step 2: fetch all OTP codes from QQ in one pass.
    _safe_print(f"qq-bulk step2: fetching OTP codes from QQ for {len(send_ok)} emails...")
    codes = inbox.wait_for_verification_codes(
        recipients=send_ok,
        timeout_s=timeout_s,
        debug=True,
        poll_interval_s=float(qq_cfg["qq_poll_interval_s"]),
        max_scan_per_poll=max(int(qq_cfg["qq_max_scan_per_poll"]), requested * 3),
        delete_on_match=bool(qq_cfg["qq_delete_fetched"]),
    )

    # Step 3: verify concurrently for emails with code.
    _safe_print(f"qq-bulk step3: verifying tokens concurrently for {len(codes)} emails...")
    success = 0
    payload_by_task: Dict[int, Dict[str, Any]] = {}
    code_by_task: Dict[int, str] = {}
    redeem_async = bool(runtime_cfg.get("redeem_async")) and bool(runtime_cfg.get("redeem_credits_enabled"))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        verify_future_map = {}
        redeem_futures: Dict[Any, int] = {}
        redeem_executor: Optional[ThreadPoolExecutor] = None
        if redeem_async:
            redeem_executor = ThreadPoolExecutor(max_workers=max(1, min(workers, 4)))

        for email in send_ok:
            if email not in codes:
                task_id = task_by_email[email]
                item_by_task[task_id]["error"] = "otp_not_received"
                continue
            task_id = task_by_email[email]
            code = codes[email]
            verify_future_map[
                executor.submit(_verify_otp, email, code, headers, 30, f"[QQ-VERIFY {task_id}]")
            ] = (task_id, email, code)

        for future in as_completed(verify_future_map):
            task_id, email, code = verify_future_map[future]
            item = item_by_task[task_id]
            try:
                verify_data = future.result()
                payload = _build_account_payload(
                    email=email,
                    verify_data=verify_data,
                    source="qq_bulk",
                    headers=headers,
                    timeout_s=timeout_s,
                    log_prefix=f"[QQ-VERIFY {task_id}]",
                    runtime_cfg=runtime_cfg,
                )
                payload_by_task[task_id] = payload
                code_by_task[task_id] = code
                if (
                    redeem_executor is not None
                    and bool(payload.get("credits_redeem_pending"))
                    and str(payload.get("source") or "").strip().lower() != "manual"
                ):
                    redeem_future = redeem_executor.submit(
                        _finalize_pending_redeem,
                        payload,
                        headers,
                        timeout_s,
                        f"[QQ-VERIFY {task_id}]",
                        runtime_cfg,
                    )
                    redeem_futures[redeem_future] = task_id
                elif bool(payload.get("credits_redeem_pending")):
                    _finalize_pending_redeem(
                        payload=payload,
                        headers=headers,
                        timeout_s=timeout_s,
                        log_prefix=f"[QQ-VERIFY {task_id}]",
                        runtime_cfg=runtime_cfg,
                    )
            except Exception as exc:
                item["error"] = f"verify_failed: {exc}"
                _safe_print(f"[QQ-VERIFY {task_id}] failed: {exc}")

        for redeem_future in as_completed(redeem_futures):
            task_id = redeem_futures[redeem_future]
            item = item_by_task.get(task_id)
            if not isinstance(item, dict):
                continue
            try:
                redeem_future.result()
            except Exception as exc:
                item["error"] = f"redeem_failed: {exc}"
                _safe_print(f"[QQ-VERIFY {task_id}] redeem failed: {exc}")

        if redeem_executor is not None:
            redeem_executor.shutdown(wait=True)

    for task_id, payload in payload_by_task.items():
        item = item_by_task.get(task_id)
        if not isinstance(item, dict):
            continue
        if item.get("error"):
            continue
        code = code_by_task.get(task_id, "")
        if mode == "jsonl":
            _append_jsonl(str(summary_out), payload)
            saved_path = str(summary_out)
        else:
            account_out = out_dir / f"nodeops_auth_token_{task_id:03d}.json"
            saved_path = _write_json(str(account_out), payload, announce=False)
        item.update(
            {
                "ok": True,
                "uuid": payload.get("uuid"),
                "token_mask": _mask_token(str(payload.get("x_auth_token") or "")),
                "otp": code,
                "deployment_id": payload.get("deployment_id"),
                "session_id": payload.get("session_id"),
                "credits_redeem_success": payload.get("credits_redeem_success"),
                "credits_redeem_status_code": payload.get("credits_redeem_status_code"),
                "output": saved_path,
            }
        )
        success += 1
        _safe_print(f"[QQ-VERIFY {task_id}] saved: {saved_path}")
        _safe_print(f"[QQ-VERIFY {task_id}] TASK_RESULT_JSON:{json.dumps(payload, ensure_ascii=False)}")

    sorted_items = sorted(items, key=lambda x: int(x["task_id"]))
    summary = {
        "created_at": _utc_now_iso(),
        "mode": "batch_qq_bulk_prefetch",
        "requested_count": requested,
        "thread_count": workers,
        "success_count": success,
        "failure_count": requested - success,
        "output_dir": str(out_dir),
        "items": sorted_items,
    }
    if mode == "dir":
        _write_json(str(summary_out), summary, announce=True)
    else:
        _safe_print("BATCH_SUMMARY_JSON:" + json.dumps(summary, ensure_ascii=False))
    _safe_print(f"qq-bulk done: success={success}/{requested}")


def _run_batch(
    count: int,
    threads: int,
    timeout_s: int,
    max_attempts: int,
    output_dir: str,
    summary_output: str,
    output_mode: str,
    headers: Dict[str, str],
    enabled_sources: List[str],
    qq_cfg: Dict[str, Any],
    outlook_cfg: Dict[str, Any],
    runtime_cfg: Dict[str, Any],
) -> None:
    requested = max(1, count)
    workers = max(1, min(threads, requested))
    mode = str(output_mode or "jsonl").strip().lower()
    if mode not in {"jsonl", "dir"}:
        raise SystemExit(f"Unsupported --output-mode value: {output_mode} (allowed: jsonl|dir)")
    summary_out = Path(summary_output).expanduser().resolve()
    summary_out.parent.mkdir(parents=True, exist_ok=True)
    out_dir = Path(output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    _safe_print(
        f"batch start: requested={requested}, threads={workers}, "
        f"sources={enabled_sources}, output_dir={out_dir}"
    )
    items: List[Dict[str, Any]] = []
    success = 0
    payloads_by_task: Dict[int, Dict[str, Any]] = {}
    errors_by_task: Dict[int, str] = {}

    redeem_async = bool(runtime_cfg.get("redeem_async")) and bool(runtime_cfg.get("redeem_credits_enabled"))

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _run_auto_once,
                i + 1,
                timeout_s,
                max_attempts,
                headers,
                enabled_sources,
                qq_cfg,
                outlook_cfg,
                runtime_cfg,
            ): (i + 1)
            for i in range(requested)
        }

        redeem_futures: Dict[Any, int] = {}
        redeem_executor: Optional[ThreadPoolExecutor] = None
        if redeem_async:
            redeem_executor = ThreadPoolExecutor(max_workers=max(1, min(workers, 4)))

        try:
            for future in as_completed(futures):
                task_id = futures[future]
                try:
                    payload = future.result()
                    payloads_by_task[task_id] = payload
                    if (
                        redeem_executor is not None
                        and bool(payload.get("credits_redeem_pending"))
                        and str(payload.get("source") or "").strip().lower() != "manual"
                    ):
                        redeem_future = redeem_executor.submit(
                            _finalize_pending_redeem,
                            payload,
                            headers,
                            timeout_s,
                            f"[T{task_id}]",
                            runtime_cfg,
                        )
                        redeem_futures[redeem_future] = task_id
                except Exception as exc:
                    errors_by_task[task_id] = str(exc)
                    _safe_print(f"[T{task_id}] failed: {exc}")

            for redeem_future in as_completed(redeem_futures):
                task_id = redeem_futures[redeem_future]
                try:
                    redeem_future.result()
                except Exception as exc:
                    errors_by_task[task_id] = str(exc)
                    _safe_print(f"[T{task_id}] redeem failed: {exc}")
        finally:
            if redeem_executor is not None:
                redeem_executor.shutdown(wait=True)

    for task_id in range(1, requested + 1):
        item: Dict[str, Any] = {"task_id": task_id}
        error = errors_by_task.get(task_id)
        payload = payloads_by_task.get(task_id)
        if error:
            item.update({"ok": False, "error": error})
            items.append(item)
            continue
        if payload is None:
            item.update({"ok": False, "error": "missing payload"})
            items.append(item)
            continue

        if mode == "jsonl":
            _append_jsonl(str(summary_out), payload)
            saved_path = str(summary_out)
        else:
            account_out = out_dir / f"nodeops_auth_token_{task_id:03d}.json"
            saved_path = _write_json(str(account_out), payload, announce=False)

        token = str(payload.get("x_auth_token") or "")
        item.update(
            {
                "ok": True,
                "source": payload.get("source"),
                "email": payload.get("email"),
                "uuid": payload.get("uuid"),
                "token_mask": _mask_token(token),
                "deployment_id": payload.get("deployment_id"),
                "session_id": payload.get("session_id"),
                "credits_redeem_success": payload.get("credits_redeem_success"),
                "credits_redeem_status_code": payload.get("credits_redeem_status_code"),
                "output": saved_path,
            }
        )
        success += 1
        _safe_print(f"[T{task_id}] saved: {saved_path}")
        _safe_print(f"[T{task_id}] TASK_RESULT_JSON:{json.dumps(payload, ensure_ascii=False)}")
        items.append(item)

    items.sort(key=lambda x: int(x.get("task_id", 0)))
    summary = {
        "created_at": _utc_now_iso(),
        "mode": "batch_auto",
        "requested_count": requested,
        "thread_count": workers,
        "sources": enabled_sources,
        "max_attempts": max_attempts,
        "success_count": success,
        "failure_count": requested - success,
        "output_dir": str(out_dir),
        "items": items,
    }
    if mode == "dir":
        _write_json(str(summary_out), summary, announce=True)
    else:
        _safe_print("BATCH_SUMMARY_JSON:" + json.dumps(summary, ensure_ascii=False))
    _safe_print(f"batch done: success={success}/{requested}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default=os.environ.get("NODEOPS_EMAIL", ""))
    parser.add_argument("--otp", default=os.environ.get("NODEOPS_OTP", ""))
    parser.add_argument("--auto-mailtm", action="store_true", help="Use mail.tm auto mailbox")
    parser.add_argument("--auto-qq", action="store_true", help="Use QQ IMAP mailbox")
    parser.add_argument("--auto-outlook", action="store_true", help="Use Hotmail/Outlook OAuth mailbox")
    parser.add_argument(
        "--source",
        default=os.environ.get("NODEOPS_BATCH_SOURCE", ""),
        help="Auto mailbox source in batch mode: mailtm|qq|outlook|both|all. Empty means auto default.",
    )
    parser.add_argument(
        "--qq-bulk-prefetch",
        action="store_true",
        help="QQ-only high-throughput mode: generate aliases, send OTP concurrently, fetch all codes once, verify concurrently",
    )
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("NODEOPS_OTP_TIMEOUT", "180")))
    parser.add_argument("--max-attempts", type=int, default=int(os.environ.get("NODEOPS_MAX_ATTEMPTS", "3")))
    parser.add_argument("--count", type=int, default=int(os.environ.get("NODEOPS_BATCH_COUNT", "1")))
    parser.add_argument("--threads", type=int, default=int(os.environ.get("NODEOPS_THREADS", "1")))
    parser.add_argument("--output", default=os.environ.get("NODEOPS_TOKEN_OUTPUT", _default_output_path()))
    parser.add_argument("--output-dir", default=os.environ.get("NODEOPS_TOKEN_OUTPUT_DIR", _default_batch_output_dir()))
    parser.add_argument(
        "--output-mode",
        default=os.environ.get("NODEOPS_OUTPUT_MODE", "jsonl"),
        choices=["jsonl", "dir"],
        help="Output mode: jsonl appends one payload per line; dir keeps per-task files + summary.",
    )
    parser.add_argument(
        "--verified-jsonl",
        default=os.environ.get("NODEOPS_VERIFIED_JSONL", ""),
        help="Append OTP-verified token payloads to this JSONL file (best-effort). Default: <output-dir>/verified_tokens.jsonl",
    )
    parser.add_argument(
        "--deployment-prompt",
        default=os.environ.get("NODEOPS_DEPLOYMENT_PROMPT", "init"),
        help="Prompt used when creating deployment.",
    )
    parser.add_argument(
        "--skip-runtime-bootstrap",
        action="store_true",
        help="Only output X-Auth-Token; skip deployment+session bootstrap.",
    )
    parser.add_argument(
        "--redeem-credits",
        type=int,
        default=int(os.environ.get("NODEOPS_REDEEM_CREDITS", "400")),
        help="Redeem this many NodeOps credits to OpenRouter right after OTP verify (default: 400).",
    )
    parser.add_argument(
        "--redeem-chunk-nodeops-credits",
        type=int,
        default=int(os.environ.get("NODEOPS_REDEEM_CHUNK_NODEOPS_CREDITS", "100")),
        help="Per-call NodeOps credit chunk for redeem (allowed by UI/API flow: 100 or 250; default: 100).",
    )
    parser.add_argument(
        "--skip-credit-redeem",
        action="store_true",
        help="Skip redeeming CreateOS credits after registration.",
    )
    parser.add_argument(
        "--credit-redeem-strict",
        action="store_true",
        help="Fail task when credit redeem request is not successful.",
    )
    parser.add_argument(
        "--redeem-async",
        action="store_true",
        help="Run credit redeem asynchronously after OTP verify (batch mode schedules redeem in a separate thread pool).",
    )
    parser.add_argument(
        "--session-empty-raw-body",
        action="store_true",
        help="Create session with empty raw body; default uses empty JSON {}.",
    )

    # QQ config defaults from user-provided setup.
    parser.add_argument("--qq-email", default=os.environ.get("NODEOPS_QQ_EMAIL", "2248500129@qq.com"))
    parser.add_argument("--qq-password", default=os.environ.get("NODEOPS_QQ_PASSWORD", "rbleglctusbjecfb"))
    parser.add_argument("--qq-imap-server", default=os.environ.get("NODEOPS_QQ_IMAP_SERVER", "imap.qq.com"))
    parser.add_argument("--qq-imap-port", type=int, default=int(os.environ.get("NODEOPS_QQ_IMAP_PORT", "993")))
    parser.add_argument("--qq-folder", default=os.environ.get("NODEOPS_QQ_FOLDER", "&UXZO1mWHTvZZOQ-/nodeops"))
    parser.add_argument("--alias-domain", default=os.environ.get("NODEOPS_ALIAS_DOMAIN", "jdjf999.ggff.net"))
    parser.add_argument("--alias-prefix-len", type=int, default=int(os.environ.get("NODEOPS_ALIAS_PREFIX_LEN", "10")))
    parser.add_argument("--qq-poll-interval-s", type=float, default=float(os.environ.get("NODEOPS_QQ_POLL_INTERVAL_S", "4")))
    parser.add_argument("--qq-max-scan-per-poll", type=int, default=int(os.environ.get("NODEOPS_QQ_MAX_SCAN_PER_POLL", "30")))
    parser.add_argument(
        "--qq-keep-fetched",
        action="store_true",
        help="Do not delete matched OTP emails after extraction (default deletes matched messages).",
    )

    parser.add_argument("--outlook-accounts-txt", default=os.environ.get("NODEOPS_OUTLOOK_ACCOUNTS_TXT", ""))
    parser.add_argument(
        "--hotmail-history-url",
        default=os.environ.get("HOTMAIL_OAUTH_HISTORY_URL", ""),
        help="zhanghaoya hotmail oauth history API url (or local oauth-card file path) for --source outlook",
    )
    parser.add_argument(
        "--outlook-folder",
        default=os.environ.get("NODEOPS_OUTLOOK_FOLDER", "auto"),
        help="Mailbox folder(s) to scan, default auto -> Inbox + Junk Email",
    )
    parser.add_argument(
        "--outlook-poll-interval-s",
        type=float,
        default=float(os.environ.get("NODEOPS_OUTLOOK_POLL_INTERVAL_S", "4")),
    )
    parser.add_argument(
        "--outlook-max-scan-per-poll",
        type=int,
        default=int(os.environ.get("NODEOPS_OUTLOOK_MAX_SCAN_PER_POLL", "20")),
    )
    parser.add_argument(
        "--outlook-keep-fetched",
        action="store_true",
        help="Do not delete matched verification emails after extraction.",
    )

    args = parser.parse_args()

    global _verified_jsonl_path
    if str(args.verified_jsonl).strip():
        _verified_jsonl_path = str(Path(str(args.verified_jsonl)).expanduser().resolve())
    else:
        _verified_jsonl_path = str(Path(str(args.output_dir)).expanduser().resolve() / "verified_tokens.jsonl")

    headers = _headers()
    count = max(1, int(args.count))
    max_attempts = max(1, int(args.max_attempts))
    timeout_s = max(30, int(args.timeout))

    enabled_sources: List[str] = []
    if args.auto_mailtm:
        enabled_sources.append("mailtm")
    if args.auto_qq:
        enabled_sources.append("qq")
    if args.auto_outlook:
        enabled_sources.append("outlook")
    enabled_sources.extend(_parse_source_mode(args.source))
    enabled_sources = _dedupe_sources(enabled_sources)

    qq_cfg = {
        "qq_email": str(args.qq_email).strip(),
        "qq_password": str(args.qq_password).strip(),
        "qq_imap_server": str(args.qq_imap_server).strip(),
        "qq_imap_port": int(args.qq_imap_port),
        "qq_folder": str(args.qq_folder).strip(),
        "alias_domain": str(args.alias_domain).strip(),
        "alias_prefix_len": int(args.alias_prefix_len),
        "qq_poll_interval_s": float(args.qq_poll_interval_s),
        "qq_max_scan_per_poll": int(args.qq_max_scan_per_poll),
        "qq_delete_fetched": not bool(args.qq_keep_fetched),
    }
    outlook_history_url = str(args.hotmail_history_url).strip()
    if not outlook_history_url:
        zhanghaoya_key = load_zhanghaoya_key()
        if zhanghaoya_key:
            outlook_history_url = f"https://www.zhanghaoya.com/store/ga/history?type=hotmail&key={zhanghaoya_key}"
    outlook_cfg: Dict[str, Any] = {
        "accounts_txt": str(args.outlook_accounts_txt).strip(),
        "history_url": outlook_history_url,
        "folder": str(args.outlook_folder).strip() or "auto",
        "poll_interval_s": float(args.outlook_poll_interval_s),
        "max_scan_per_poll": int(args.outlook_max_scan_per_poll),
        "delete_fetched": not bool(args.outlook_keep_fetched),
        "cards": [],
    }
    if "outlook" in enabled_sources:
        if not outlook_cfg["accounts_txt"]:
            raise SystemExit("--source=outlook requires --outlook-accounts-txt")
        if not outlook_cfg["history_url"]:
            raise SystemExit("--source=outlook requires --hotmail-history-url (or a configured zhanghaoya key file)")
        accounts = load_outlook_accounts(outlook_cfg["accounts_txt"])
        if len(accounts) < count:
            raise SystemExit(f"outlook accounts file has {len(accounts)} entries, but --count={count}")
        cards = load_hotmail_oauth_cards_from_zhanghaoya(
            outlook_cfg["history_url"],
            timeout_s=30.0,
            max_attempts=3,
            logger=lambda msg: _safe_print(f"[outlook] {msg}"),
        )
        card_by_email = {str(e).strip().lower(): (e, pw, cid, rt) for (e, pw, cid, rt) in cards}
        picked_cards: List[Any] = []
        for email, _password in accounts[:count]:
            card = card_by_email.get(str(email).strip().lower())
            if not card:
                raise SystemExit(f"hotmail oauth card not found in history for: {email}")
            picked_cards.append(card)
        outlook_cfg["cards"] = picked_cards

    runtime_cfg = {
        "create_runtime": not bool(args.skip_runtime_bootstrap),
        "deployment_prompt": str(args.deployment_prompt),
        "session_empty_raw_body": bool(args.session_empty_raw_body),
        "redeem_credits_enabled": not bool(args.skip_credit_redeem),
        "redeem_credits_amount": int(max(0, int(args.redeem_credits))),
        "redeem_chunk_nodeops_credits": int(args.redeem_chunk_nodeops_credits),
        "redeem_credits_strict": bool(args.credit_redeem_strict),
        "redeem_async": bool(args.redeem_async),
    }

    if count > 1:
        if not enabled_sources:
            enabled_sources = ["mailtm", "qq"]
        if args.qq_bulk_prefetch:
            if enabled_sources != ["qq"]:
                raise SystemExit("--qq-bulk-prefetch requires QQ-only mode (use --auto-qq and do not add --auto-mailtm)")
            _run_batch_qq_prefetch(
                count=count,
                threads=max(1, int(args.threads)),
                timeout_s=timeout_s,
                output_dir=args.output_dir,
                summary_output=args.output,
                output_mode=args.output_mode,
                headers=headers,
                qq_cfg=qq_cfg,
                runtime_cfg=runtime_cfg,
            )
            return
        _run_batch(
            count=count,
            threads=max(1, int(args.threads)),
            timeout_s=timeout_s,
            max_attempts=max_attempts,
            output_dir=args.output_dir,
            summary_output=args.output,
            output_mode=args.output_mode,
            headers=headers,
            enabled_sources=enabled_sources,
            qq_cfg=qq_cfg,
            outlook_cfg=outlook_cfg,
            runtime_cfg=runtime_cfg,
        )
        return

    email = str(args.email or "").strip()
    otp = str(args.otp or "").strip()

    if enabled_sources:
        payload = _run_auto_once(
            task_id=1,
            timeout_s=timeout_s,
            max_attempts=max_attempts,
            headers=headers,
            enabled_sources=enabled_sources,
            qq_cfg=qq_cfg,
            outlook_cfg=outlook_cfg,
            runtime_cfg=runtime_cfg,
        )
        if bool(payload.get("credits_redeem_pending")):
            _finalize_pending_redeem(
                payload=payload,
                headers=headers,
                timeout_s=timeout_s,
                log_prefix="[T1]",
                runtime_cfg=runtime_cfg,
            )
        if str(args.output_mode).strip().lower() == "jsonl":
            out = Path(str(args.output)).expanduser().resolve()
            _append_jsonl(str(out), payload)
            _safe_print(f"[T1] saved: {out}")
            _safe_print(f"[T1] TASK_RESULT_JSON:{json.dumps(payload, ensure_ascii=False)}")
            _safe_print(
                "BATCH_SUMMARY_JSON:"
                + json.dumps(
                    {
                        "created_at": _utc_now_iso(),
                        "mode": "single_auto_jsonl",
                        "requested_count": 1,
                        "thread_count": 1,
                        "sources": enabled_sources,
                        "max_attempts": max_attempts,
                        "success_count": 1,
                        "failure_count": 0,
                        "output_dir": str(Path(args.output_dir).expanduser().resolve()),
                        "items": [
                            {
                                "task_id": 1,
                                "ok": True,
                                "source": payload.get("source"),
                                "email": payload.get("email"),
                                "uuid": payload.get("uuid"),
                                "token_mask": _mask_token(str(payload.get("x_auth_token") or "")),
                                "deployment_id": payload.get("deployment_id"),
                                "session_id": payload.get("session_id"),
                                "credits_redeem_success": payload.get("credits_redeem_success"),
                                "credits_redeem_status_code": payload.get("credits_redeem_status_code"),
                                "output": str(out),
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
            )
            return
    else:
        if not email:
            raise SystemExit("Missing --email (or NODEOPS_EMAIL)")
        payload = _run_single_manual(
            email=email,
            otp=otp,
            headers=headers,
            timeout_s=timeout_s,
            runtime_cfg=runtime_cfg,
        )
        if payload is None:
            return

    _write_json(args.output, payload, announce=True)


if __name__ == "__main__":
    main()
