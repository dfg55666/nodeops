"""Session & message proxy routes — direct access to NodeOps runtime."""
from datetime import datetime, timezone
import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from backend.services import nodeops_client as noc
from backend.services import account_pool
from backend.storage.file_store import (
    append_md,
    read_md,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
logger = logging.getLogger(__name__)


class ModelRef(BaseModel):
    providerID: str = "openrouter"
    modelID: str


class SendMessageRequest(BaseModel):
    text: str | None = None
    image_url: str | None = None
    image_mime: str | None = None
    no_reply: bool = False
    system: str | None = None
    model: ModelRef | None = None
    project_name: str | None = None
    task_id: str | None = None
    account: str | None = None
    session_file: str | None = None


@router.get("/list")
async def list_sessions(account_id: str):
    """List all sessions for an account's deployment."""
    acc = account_pool.get_account(account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    if not acc.get("runtime_host") or not acc.get("project_token"):
        raise HTTPException(400, "Account has no active deployment")

    data = await noc.list_sessions(
        acc["runtime_host"], acc["project_token"], acc["auth_token"]
    )
    return {"success": True, "data": data}


@router.get("/{session_id}/messages")
async def get_messages(session_id: str, account_id: str):
    """Pull messages for a specific session."""
    acc = account_pool.get_account(account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    if not acc.get("runtime_host") or not acc.get("project_token"):
        raise HTTPException(400, "Account has no active deployment")

    data = await noc.get_messages(
        acc["runtime_host"], acc["project_token"], acc["auth_token"], session_id
    )
    return {"success": True, "data": data}


@router.post("/{session_id}/message")
async def send_message(session_id: str, account_id: str, req: SendMessageRequest):
    """Send a message to a session."""
    acc = account_pool.get_account(account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    if not acc.get("runtime_host") or not acc.get("project_token"):
        raise HTTPException(400, "Account has no active deployment")

    if not str(req.text or "").strip() and not str(req.image_url or "").strip():
        raise HTTPException(400, "text or image_url is required")

    requested_model = req.model.modelID if req.model else ""
    logger.info(
        "Session send request: session_id=%s account_id=%s account_email=%s text_len=%s has_image=%s model=%s",
        session_id,
        account_id,
        acc.get("email"),
        len(str(req.text or "")),
        bool(str(req.image_url or "").strip()),
        requested_model or "<session-default>",
    )

    try:
        data = await noc.send_message(
            acc["runtime_host"], acc["project_token"], acc["auth_token"],
            session_id,
            req.text or "",
            req.no_reply,
            req.system,
            req.model.model_dump() if req.model else None,
            image_url=req.image_url,
            image_mime=req.image_mime,
        )
    except Exception as exc:
        err_message = str(exc)
        logger.exception(
            "Session send transport error: session_id=%s account_id=%s account_email=%s model=%s",
            session_id,
            account_id,
            acc.get("email"),
            requested_model or "<session-default>",
        )
        if _should_mark_account_exhausted(err_message):
            try:
                account_pool.mark_account_status(account_id, "exhausted")
            except Exception:
                logger.exception(
                    "Failed to mark account exhausted after transport error: account_id=%s",
                    account_id,
                )
        raise HTTPException(502, f"Upstream send failed: {err_message}")

    runtime_error = _extract_runtime_error(data)
    if runtime_error is not None:
        err_message = str(runtime_error.get("message") or "Upstream runtime error")
        model_id = str(runtime_error.get("model_id") or requested_model or "")
        provider_id = str(runtime_error.get("provider_id") or "")
        status_code = runtime_error.get("status_code")
        logger.warning(
            "Session send upstream error: session_id=%s account_id=%s model=%s provider=%s status=%s message=%s",
            session_id,
            account_id,
            model_id or "<unknown>",
            provider_id or "<unknown>",
            status_code,
            err_message,
        )
        if _should_mark_account_exhausted(err_message):
            try:
                account_pool.mark_account_status(account_id, "exhausted")
            except Exception:
                logger.exception(
                    "Failed to mark account exhausted after send error: account_id=%s",
                    account_id,
                )
        detail = err_message
        if status_code is not None:
            detail = f"[{status_code}] {detail}"
        if model_id:
            detail = f"{detail} | model={model_id}"
        raise HTTPException(502, detail)

    # Best-effort local history append so SessionView can immediately show
    # user-sent messages for manual sessions.
    try:
        _append_local_user_message(
            session_id=session_id,
            text=req.text or "",
            has_image=bool(str(req.image_url or "").strip()),
            project_name=req.project_name,
            task_id=req.task_id,
            account=req.account,
            session_file=req.session_file,
        )
    except Exception:
        # Don't fail upstream send for local history issues.
        logger.exception(
            "Failed appending local user message: session_id=%s project=%s task=%s account=%s session_file=%s",
            session_id,
            req.project_name,
            req.task_id,
            req.account,
            req.session_file,
        )

    return {"success": True, "data": data}


@router.post("/{session_id}/abort")
async def abort_session(session_id: str, account_id: str):
    """Abort current generation in a session."""
    acc = account_pool.get_account(account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    if not acc.get("runtime_host") or not acc.get("project_token"):
        raise HTTPException(400, "Account has no active deployment")

    data = await noc.abort_session(
        acc["runtime_host"], acc["project_token"], acc["auth_token"], session_id
    )
    return {"success": True, "data": data}


@router.get("/history/{project_name}/{task_id}")
def get_session_history(project_name: str, task_id: str):
    """List all saved session .md files for a task."""
    # Scan .nodeops/{task_id}/ for session files
    from backend.storage.file_store import repo_dir
    nodeops_dir = repo_dir(project_name) / ".nodeops" / task_id
    if not nodeops_dir.exists():
        return {"success": True, "data": []}

    sessions = []
    for account_dir in sorted(nodeops_dir.iterdir()):
        if account_dir.is_dir():
            for md_file in sorted(account_dir.glob("session-*.md")):
                raw = read_md(md_file)
                account_email = _extract_header_value(raw, "Account") or _decode_account_dir_name(account_dir.name)
                session_id = _extract_header_value(raw, "NodeOps Session ID")
                sessions.append({
                    "account_dir": account_dir.name,
                    "account": account_dir.name,
                    "account_email": account_email,
                    "email": account_email,
                    "file": md_file.name,
                    "session_file": md_file.name,
                    "path": str(md_file.relative_to(repo_dir(project_name))),
                    "session_id": session_id,
                })
    return {"success": True, "data": sessions}


@router.get("/history/{project_name}/{task_id}/content")
def get_session_content(project_name: str, task_id: str,
                        account: str = Query(...),
                        session_file: str = Query(...)):
    """Read the content of a session .md file."""
    from backend.storage.file_store import repo_dir
    path = repo_dir(project_name) / ".nodeops" / task_id / account / session_file
    if not path.exists():
        encoded_account = account.replace("@", "_at_").replace("+", "_plus_")
        alt = repo_dir(project_name) / ".nodeops" / task_id / encoded_account / session_file
        if alt.exists():
            path = alt
    if not path.exists():
        raise HTTPException(404, "Session file not found")
    content = read_md(path)
    return {"success": True, "data": {"content": content}}


def _extract_header_value(raw: str, key: str) -> str | None:
    if not raw:
        return None
    prefix = f"- {key}:"
    for line in raw.splitlines()[:30]:
        if line.startswith(prefix):
            value = line[len(prefix):].strip()
            return value or None
    return None


def _decode_account_dir_name(value: str) -> str:
    return str(value or "").replace("_plus_", "+").replace("_at_", "@")


def _append_local_user_message(
    session_id: str,
    text: str,
    has_image: bool,
    project_name: str | None,
    task_id: str | None,
    account: str | None,
    session_file: str | None,
):
    from backend.storage.file_store import repo_dir

    pn = str(project_name or "").strip()
    tid = str(task_id or "").strip()
    sf = str(session_file or "").strip()
    if not pn or not tid or not sf:
        return

    base = repo_dir(pn) / ".nodeops" / tid
    if not base.exists():
        return

    candidates = []
    raw_account = str(account or "").strip()
    if raw_account:
        candidates.append(base / raw_account / sf)
        encoded = raw_account.replace("@", "_at_").replace("+", "_plus_")
        candidates.append(base / encoded / sf)

    if not candidates:
        for account_dir in base.iterdir():
            if account_dir.is_dir():
                candidates.append(account_dir / sf)

    target = None
    for p in candidates:
        if not p.exists():
            continue
        raw = read_md(p)
        sid = _extract_header_value(raw, "NodeOps Session ID")
        if sid and sid == session_id:
            target = p
            break

    if target is None:
        return

    content = str(text or "").strip()
    if not content and has_image:
        content = "[image]"
    if not content:
        return

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    append_md(target, f"[User] {ts}\n{content}\n\n")


def _extract_runtime_error(payload: object) -> dict | None:
    if not isinstance(payload, dict):
        return None
    info = payload.get("info")
    if not isinstance(info, dict):
        return None
    err = info.get("error")
    if not isinstance(err, dict):
        return None
    err_data = err.get("data") if isinstance(err.get("data"), dict) else {}
    message = str(
        err_data.get("message")
        or err.get("message")
        or ""
    ).strip()
    raw_status = err_data.get("statusCode") or err_data.get("status_code")
    status_code = None
    try:
        if raw_status is not None and str(raw_status).strip():
            status_code = int(raw_status)
    except Exception:
        status_code = None
    return {
        "name": err.get("name"),
        "message": message,
        "status_code": status_code,
        "model_id": info.get("modelID"),
        "provider_id": info.get("providerID"),
    }


def _should_mark_account_exhausted(message: str) -> bool:
    msg = str(message or "").strip().lower()
    if not msg:
        return False
    if "key limit exceeded" in msg:
        return True
    # Keep this stricter than generic "limit" to avoid false positives on
    # transient rate limits or unrelated upstream constraints.
    return any(kw in msg for kw in (
        "credit",
        "quota",
        "insufficient",
        "no remaining",
        "exhausted",
        "not enough",
        "balance",
    ))
