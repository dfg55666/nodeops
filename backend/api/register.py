"""
Registration API routes.

POST /api/register/send-otp          — send OTP to email
POST /api/register/verify            — verify OTP manually, full flow
POST /api/register/gmail-auto        — Gmail auto single account
POST /api/register/gmail-batch       — Gmail auto batch
POST /api/register/fetch-otp         — fetch latest OTP from Gmail (debug/manual assist)
GET  /api/register/aliases           — generate Gmail plus-address aliases preview
"""
from __future__ import annotations

import asyncio
import json
import os
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.services.register import (
    GmailConfig,
    RegisterConfig,
    RegisterResult,
    send_otp,
    verify_otp,
    register_account,
    gmail_auto_register,
    batch_gmail_register,
    generate_gmail_aliases,
)
from backend.services.gmail_imap import GmailIMAPInbox

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/register", tags=["register"])

# ── Default Gmail credentials (from env or hardcoded fallback) ─────────────
_DEFAULT_GMAIL = os.environ.get("NODEOPS_GMAIL", "feijidfg55@gmail.com")
_DEFAULT_APP_PW = os.environ.get("NODEOPS_GMAIL_APP_PASSWORD", "maqk srdy ucjq bsby")
_DEFAULT_PROXY_HOST = os.environ.get("NODEOPS_PROXY_HOST", "127.0.0.1")
_DEFAULT_PROXY_PORT = int(os.environ.get("NODEOPS_PROXY_PORT", "7897"))
_DEFAULT_PROXY_TYPE = os.environ.get("NODEOPS_PROXY_TYPE", "http")


# ── Request / Response models ──────────────────────────────────────────────

class SendOtpRequest(BaseModel):
    email: str


class VerifyRequest(BaseModel):
    email: str
    otp: str
    redeem_credits: bool = False
    redeem_amount: int = 400
    redeem_chunk: int = 100
    create_runtime: bool = True
    save_to_pool: bool = True


class GmailAutoRequest(BaseModel):
    """Single-account Gmail auto-register."""
    target_email: str = Field(..., description="NodeOps account email (can be Gmail alias)")
    # Gmail inbox credentials
    gmail_email: str = Field(default="", description="Gmail address for IMAP (default from env)")
    gmail_app_password: str = Field(default="", description="Gmail app password (default from env)")
    # Proxy
    proxy_host: str = Field(default="", description="Proxy host (default from env)")
    proxy_port: int = Field(default=0, description="Proxy port (default from env)")
    proxy_type: str = Field(default="http")
    # IMAP tuning
    lookback_hours: int = 72
    max_mails: int = 120
    delete_best: bool = True
    poll_interval_s: float = 5.0
    otp_timeout_s: int = 180
    # Registration options
    redeem_credits: bool = False
    redeem_amount: int = 400
    redeem_chunk: int = 100
    create_runtime: bool = True
    save_to_pool: bool = True


class GmailBatchRequest(BaseModel):
    """Batch Gmail auto-register via plus-addressing."""
    count: int = Field(default=1, ge=1, le=50)
    base_email: str = Field(default="", description="Base Gmail address; default from env")
    gmail_app_password: str = Field(default="")
    proxy_host: str = Field(default="")
    proxy_port: int = Field(default=0)
    proxy_type: str = Field(default="http")
    lookback_hours: int = 72
    max_mails: int = 120
    delete_best: bool = True
    poll_interval_s: float = 5.0
    otp_timeout_s: int = 180
    concurrency: int = Field(default=3, ge=1, le=20)
    redeem_credits: bool = False
    redeem_amount: int = 400
    redeem_chunk: int = 100
    create_runtime: bool = True
    save_to_pool: bool = True


class FetchOtpRequest(BaseModel):
    """Manually trigger Gmail OTP fetch (for debugging)."""
    gmail_email: str = Field(default="")
    gmail_app_password: str = Field(default="")
    proxy_host: str = Field(default="")
    proxy_port: int = Field(default=0)
    proxy_type: str = Field(default="http")
    to_email_contains: str = Field(default="")
    delete_best: bool = False
    lookback_hours: int = 72
    max_mails: int = 120


class AliasesRequest(BaseModel):
    base_email: str = Field(default="")
    count: int = Field(default=5, ge=1, le=100)


# ── Helpers ────────────────────────────────────────────────────────────────

def _gmail_cfg(req_email: str, req_pw: str, req_proxy_host: str,
               req_proxy_port: int, req_proxy_type: str,
               **kwargs) -> GmailConfig:
    return GmailConfig(
        email=req_email.strip() or _DEFAULT_GMAIL,
        app_password=req_pw.strip() or _DEFAULT_APP_PW,
        proxy_host=req_proxy_host.strip() or _DEFAULT_PROXY_HOST,
        proxy_port=req_proxy_port or _DEFAULT_PROXY_PORT,
        proxy_type=req_proxy_type.strip() or _DEFAULT_PROXY_TYPE,
        **kwargs,
    )


def _reg_cfg(redeem: bool, amount: int, chunk: int,
             create_rt: bool) -> RegisterConfig:
    return RegisterConfig(
        redeem_credits=redeem,
        redeem_amount_nodeops=amount,
        redeem_chunk_nodeops=chunk,
        create_runtime=create_rt,
    )


def _result_resp(r: RegisterResult) -> dict:
    return {"success": r.ok, "data": r.to_dict()}


def _sse_event(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── Routes ─────────────────────────────────────────────────────────────────

@router.post("/send-otp")
async def api_send_otp(req: SendOtpRequest):
    """Send OTP email to the given address via NodeOps auth service."""
    try:
        resp = await send_otp(req.email.strip())
        return {"success": True, "data": resp}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/verify")
async def api_verify(req: VerifyRequest):
    """
    Verify OTP manually and run the full registration flow
    (redeem credits + bootstrap runtime + save to pool).
    """
    cfg = _reg_cfg(req.redeem_credits, req.redeem_amount, req.redeem_chunk, req.create_runtime)
    try:
        result = await register_account(
            email=req.email.strip(),
            otp=req.otp.strip(),
            cfg=cfg,
            save_to_pool=req.save_to_pool,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if not result.ok:
        raise HTTPException(status_code=400, detail=result.error)
    return _result_resp(result)


@router.post("/gmail-auto")
async def api_gmail_auto(req: GmailAutoRequest):
    """
    Fully automatic single-account registration via Gmail IMAP.
    Sends OTP to target_email, polls Gmail inbox, verifies, optionally
    redeems credits and bootstraps runtime, then saves to account pool.
    """
    gcfg = _gmail_cfg(
        req.gmail_email, req.gmail_app_password,
        req.proxy_host, req.proxy_port, req.proxy_type,
        lookback_hours=req.lookback_hours,
        max_mails=req.max_mails,
        delete_best=req.delete_best,
        poll_interval_s=req.poll_interval_s,
        otp_timeout_s=req.otp_timeout_s,
    )
    rcfg = _reg_cfg(req.redeem_credits, req.redeem_amount, req.redeem_chunk, req.create_runtime)

    try:
        result = await gmail_auto_register(
            target_email=req.target_email.strip(),
            gmail_cfg=gcfg,
            reg_cfg=rcfg,
            save_to_pool=req.save_to_pool,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if not result.ok:
        raise HTTPException(status_code=400, detail=result.error)
    return _result_resp(result)


@router.post("/gmail-batch")
async def api_gmail_batch(req: GmailBatchRequest):
    """
    Batch automatic registration via Gmail plus-addressing.
    Generates `count` aliases with random 4-char suffix after '+',
    registers them concurrently, returns per-account results.
    """
    base = req.base_email.strip() or _DEFAULT_GMAIL
    aliases = generate_gmail_aliases(base, req.count)

    gcfg = _gmail_cfg(
        base, req.gmail_app_password,
        req.proxy_host, req.proxy_port, req.proxy_type,
        lookback_hours=req.lookback_hours,
        max_mails=req.max_mails,
        delete_best=req.delete_best,
        poll_interval_s=req.poll_interval_s,
        otp_timeout_s=req.otp_timeout_s,
    )
    rcfg = _reg_cfg(req.redeem_credits, req.redeem_amount, req.redeem_chunk, req.create_runtime)

    try:
        results = await batch_gmail_register(
            emails=aliases,
            gmail_cfg=gcfg,
            reg_cfg=rcfg,
            concurrency=req.concurrency,
            save_to_pool=req.save_to_pool,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    items = [r.to_dict() for r in results]
    success_count = sum(1 for r in results if r.ok)
    return {
        "success": True,
        "data": {
            "total": len(results),
            "success_count": success_count,
            "failure_count": len(results) - success_count,
            "aliases": aliases,
            "items": items,
        },
    }


@router.post("/gmail-batch/stream")
async def api_gmail_batch_stream(req: GmailBatchRequest):
    """
    Streaming batch registration endpoint (SSE).
    Emits:
      - event: meta   (aliases + total)
      - event: log    (step logs from register service)
      - event: result (final aggregate result)
      - event: error  (fatal error)
      - event: end
    """
    base = req.base_email.strip() or _DEFAULT_GMAIL
    aliases = generate_gmail_aliases(base, req.count)

    gcfg = _gmail_cfg(
        base, req.gmail_app_password,
        req.proxy_host, req.proxy_port, req.proxy_type,
        lookback_hours=req.lookback_hours,
        max_mails=req.max_mails,
        delete_best=req.delete_best,
        poll_interval_s=req.poll_interval_s,
        otp_timeout_s=req.otp_timeout_s,
    )
    rcfg = _reg_cfg(req.redeem_credits, req.redeem_amount, req.redeem_chunk, req.create_runtime)

    q: asyncio.Queue[dict | None] = asyncio.Queue()

    async def _log_hook(payload: dict):
        await q.put({"event": "log", "data": payload})

    async def _runner():
        try:
            results = await batch_gmail_register(
                emails=aliases,
                gmail_cfg=gcfg,
                reg_cfg=rcfg,
                concurrency=req.concurrency,
                save_to_pool=req.save_to_pool,
                log_hook=_log_hook,
            )
            items = [r.to_dict() for r in results]
            success_count = sum(1 for r in results if r.ok)
            await q.put({
                "event": "result",
                "data": {
                    "total": len(results),
                    "success_count": success_count,
                    "failure_count": len(results) - success_count,
                    "aliases": aliases,
                    "items": items,
                },
            })
        except Exception as exc:
            await q.put({
                "event": "error",
                "data": {"message": str(exc)},
            })
        finally:
            await q.put(None)

    runner_task = asyncio.create_task(_runner())

    async def _event_stream():
        try:
            yield _sse_event("meta", {"total": len(aliases), "aliases": aliases})
            while True:
                item = await q.get()
                if item is None:
                    yield _sse_event("end", {"ok": True})
                    break
                yield _sse_event(str(item.get("event") or "log"), item.get("data", {}))
        finally:
            if not runner_task.done():
                runner_task.cancel()
                try:
                    await runner_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/fetch-otp")
async def api_fetch_otp(req: FetchOtpRequest):
    """
    Fetch the latest verification OTP from Gmail inbox.
    Useful for manual assist or debugging when you've already sent the OTP
    but want the backend to retrieve the code for you.
    """
    inbox = GmailIMAPInbox(
        email_addr=req.gmail_email.strip() or _DEFAULT_GMAIL,
        app_password=req.gmail_app_password.strip() or _DEFAULT_APP_PW,
        proxy_type=req.proxy_type or _DEFAULT_PROXY_TYPE,
        proxy_host=req.proxy_host.strip() or _DEFAULT_PROXY_HOST,
        proxy_port=req.proxy_port or _DEFAULT_PROXY_PORT,
        lookback_hours=req.lookback_hours,
        max_mails=req.max_mails,
    )
    try:
        result = await inbox.fetch_latest_code(
            to_email_contains=req.to_email_contains.strip(),
            delete_best=req.delete_best,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if not result.ok:
        raise HTTPException(status_code=404, detail=result.error)
    return {"success": True, "data": result.to_dict()}


@router.post("/aliases")
async def api_aliases(req: AliasesRequest):
    """Preview Gmail plus-address aliases that would be used in batch mode."""
    base = req.base_email.strip() or _DEFAULT_GMAIL
    aliases = generate_gmail_aliases(base, req.count)
    return {"success": True, "data": {"base_email": base, "aliases": aliases}}
