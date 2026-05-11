"""Session & message proxy routes — direct access to NodeOps runtime."""
import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import time
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from backend.services import nodeops_client as noc
from backend.services import account_pool
from backend.services import credit_monitor
from backend.services import task_engine
from backend.services.message_utils import (
    extract_message_role,
    extract_message_text,
    normalize_chat_role,
    normalize_messages,
)
from backend.services.sse_parser import parse_sse_payloads
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

    if not str(req.text or "").strip() and not str(req.image_url or "").strip():
        raise HTTPException(400, "text or image_url is required")

    runtime_host = str(acc.get("runtime_host") or "").strip()
    project_token = str(acc.get("project_token") or "").strip()
    effective_session_id = str(session_id or "").strip()
    task_bound_send = bool(req.project_name and req.task_id)
    task_state = None
    task_bound_account_id = ""
    if task_bound_send:
        task_state = task_engine.get_task(str(req.project_name or ""), str(req.task_id or ""))
        if isinstance(task_state, dict):
            # Task-bound sends must use task-scoped runtime/session state.
            # Do not fallback to account cached runtime; that may point to a different deployment.
            runtime_host = str(task_state.get("current_runtime_host") or "").strip()
            project_token = str(task_state.get("current_project_token") or "").strip()
            task_bound_account_id = str(task_state.get("current_account_id") or "").strip()
            if task_bound_account_id and task_bound_account_id != account_id:
                task_acc = account_pool.get_account(task_bound_account_id)
                if task_acc:
                    acc = task_acc
                    account_id = task_bound_account_id

    local_or_pending_session = (
        not effective_session_id
        or effective_session_id == "local-pending"
        or effective_session_id.startswith("local-")
    )
    need_bootstrap = bool(
        task_bound_send
        and (
            local_or_pending_session
            or not runtime_host
            or not project_token
        )
    )
    prompt_for_runtime = (
        str(req.text or "").strip()
        or str(req.system or "").strip()
        or ("image-input" if str(req.image_url or "").strip() else "")
    )
    if need_bootstrap:
        try:
            runtime_host, project_token, effective_session_id = await _bootstrap_fresh_runtime_session_for_task_send(
                req=req,
                account_id=account_id,
                account=acc,
                prompt_for_runtime=prompt_for_runtime,
            )
        except Exception as exc:
            logger.warning(
                "Failed to bootstrap fresh runtime/session for send: project=%s task=%s account=%s err=%s",
                req.project_name,
                req.task_id,
                account_id,
                exc,
            )
            raise HTTPException(502, f"Create fresh deployment/session failed: {exc}")
    elif not runtime_host or not project_token:
        # Non-task manual send still uses account cached runtime.
        raise HTTPException(400, "Account has no active deployment")

    if not runtime_host or not project_token:
        raise HTTPException(400, "Account has no active deployment")
    if not effective_session_id:
        raise HTTPException(400, "session_id is required")

    requested_model = req.model.modelID if req.model else ""
    logger.info(
        "Session send request: session_id=%s account_id=%s account_email=%s task_bound=%s task_bound_account=%s text_len=%s has_image=%s model=%s",
        session_id,
        account_id,
        acc.get("email"),
        task_bound_send,
        task_bound_account_id or "",
        len(str(req.text or "")),
        bool(str(req.image_url or "").strip()),
        requested_model or "<session-default>",
    )

    data = None
    credit_error_after_send = ""
    monitor_credit_sse = bool(req.project_name and req.task_id and not bool(req.no_reply))
    send_attempts = 3
    for send_attempt in range(1, send_attempts + 1):
        sse_state: dict[str, object] = {"credit_exhausted": False, "message": ""}
        sse_task = None
        if monitor_credit_sse:
            sse_task = asyncio.create_task(
                _watch_credit_exhausted_sse(
                    runtime_host=runtime_host,
                    project_token=project_token,
                    session_id=effective_session_id,
                    state=sse_state,
                )
            )
        try:
            data = await noc.send_message(
                runtime_host, project_token, acc["auth_token"],
                effective_session_id,
                req.text or "",
                req.no_reply,
                req.system,
                req.model.model_dump() if req.model else None,
                image_url=req.image_url,
                image_mime=req.image_mime,
            )
            if sse_task is not None:
                try:
                    timeout_s = float(
                        os.environ.get("NODEOPS_SEND_SSE_CREDIT_CHECK_TIMEOUT_S", "8")
                    )
                except Exception:
                    timeout_s = 8.0
                try:
                    await asyncio.wait_for(asyncio.shield(sse_task), timeout=timeout_s)
                except TimeoutError:
                    pass
                except Exception:
                    logger.debug(
                        "SSE watcher failed during send: session=%s account=%s",
                        effective_session_id,
                        account_id,
                        exc_info=True,
                    )
                if bool(sse_state.get("credit_exhausted")):
                    credit_error_after_send = str(
                        sse_state.get("message") or "credits exhausted"
                    )
            break
        except Exception as exc:
            err_message = str(exc)
            should_retry = send_attempt < send_attempts and _is_transient_upstream_error(err_message)
            if should_retry:
                if need_bootstrap:
                    logger.warning(
                        "Transient send failure (attempt %s/%s), rebuilding runtime/session and retrying: %s",
                        send_attempt,
                        send_attempts,
                        err_message,
                    )
                    try:
                        runtime_host, project_token, effective_session_id = await _bootstrap_fresh_runtime_session_for_task_send(
                            req=req,
                            account_id=account_id,
                            account=acc,
                            prompt_for_runtime=prompt_for_runtime,
                        )
                    except Exception as bootstrap_exc:
                        logger.warning(
                            "Re-bootstrap failed after transient send failure: %s",
                            bootstrap_exc,
                        )
                        raise HTTPException(502, f"Create fresh deployment/session failed: {bootstrap_exc}")
                else:
                    wait_s = min(2 ** (send_attempt - 1), 3)
                    logger.warning(
                        "Transient send failure (attempt %s/%s), retrying same session after %ss: %s",
                        send_attempt,
                        send_attempts,
                        wait_s,
                        err_message,
                    )
                    await asyncio.sleep(wait_s)
                continue

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
        finally:
            if sse_task is not None and not sse_task.done():
                sse_task.cancel()
            if sse_task is not None:
                try:
                    await sse_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

    if data is None:
        raise HTTPException(502, "Upstream send failed: empty response")

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
            session_id=effective_session_id,
            text=req.text or "",
            has_image=bool(str(req.image_url or "").strip()),
            project_name=req.project_name,
            task_id=req.task_id,
            session_file=req.session_file,
        )
        # Background sync assistant/user messages from upstream so
        # session .md stays aligned with runtime chat output.
        if req.project_name and req.task_id and req.session_file:
            sent_user_message_id = _extract_send_response_message_id(data)
            asyncio.create_task(
                _sync_session_file_from_runtime(
                    project_name=req.project_name,
                    task_id=req.task_id,
                    session_file=req.session_file,
                    runtime_host=runtime_host,
                    project_token=project_token,
                    auth_token=acc["auth_token"],
                    account_id=account_id,
                    session_id=effective_session_id,
                    sent_user_message_id=sent_user_message_id,
                    sent_user_text=str(req.text or "").strip(),
                )
            )
    except Exception:
        # Don't fail upstream send for local history issues.
        logger.exception(
            "Failed appending local user message: session_id=%s project=%s task=%s session_file=%s",
            session_id,
            req.project_name,
            req.task_id,
            req.session_file,
        )

    if credit_error_after_send:
        try:
            account_pool.mark_account_status(account_id, "exhausted")
        except Exception:
            logger.exception(
                "Failed to mark account exhausted after SSE credit error: account_id=%s",
                account_id,
            )
        raise HTTPException(502, credit_error_after_send)

    return {"success": True, "data": data, "effective_session_id": effective_session_id}


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
    from backend.storage.file_store import repo_dir
    nodeops_dir = repo_dir(project_name) / ".nodeops" / task_id
    if not nodeops_dir.exists():
        return {"success": True, "data": []}

    sessions = []

    # New layout: .nodeops/<task_id>/session-<n>.md (flat, no account subfolder)
    for md_file in sorted(nodeops_dir.glob("session-*.md")):
        raw = read_md(md_file)
        account_email = _extract_header_value(raw, "Account") or ""
        session_id = _extract_header_value(raw, "NodeOps Session ID")
        sessions.append({
            "account_email": account_email,
            "session_file": md_file.name,
            "path": str(md_file.relative_to(repo_dir(project_name))),
            "session_id": session_id,
        })
    return {"success": True, "data": sessions}


@router.get("/history/{project_name}/{task_id}/content")
async def get_session_content(project_name: str, task_id: str,
                              session_file: str = Query(...),
                              account_id: str | None = Query(None),
                              refresh_runtime: bool = Query(False)):
    """Read the content of a session .md file."""
    from backend.storage.file_store import repo_dir
    base = repo_dir(project_name) / ".nodeops" / task_id
    path = base / session_file
    if not path.exists():
        raise HTTPException(404, "Session file not found")
    content = read_md(path)
    runtime_messages: list[dict] | None = None
    if refresh_runtime:
        try:
            runtime_messages = await _refresh_session_file_once_from_runtime(
                path=path,
                project_name=project_name,
                task_id=task_id,
                account_id=account_id,
                current_content=content,
            )
            content = read_md(path)
        except Exception:
            logger.debug(
                "session refresh failed: project=%s task=%s file=%s account=%s",
                project_name,
                task_id,
                session_file,
                account_id,
                exc_info=True,
            )
    messages = runtime_messages if isinstance(runtime_messages, list) else _parse_session_messages(content)
    return {"success": True, "data": {"content": content, "messages": messages}}


def _extract_header_value(raw: str, key: str) -> str | None:
    if not raw:
        return None
    prefix = f"- {key}:"
    for line in raw.splitlines()[:30]:
        if line.startswith(prefix):
            value = line[len(prefix):].strip()
            return value or None
    return None


_ROLE_LINE_RE = re.compile(r"^\*{0,2}\[(User|Assistant)\]\*{0,2}\s*(.*)$", re.IGNORECASE)
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:\d{2})?\s*")


def _parse_session_messages(raw: str) -> list[dict]:
    if not raw:
        return []

    out: list[dict] = []
    current_role = ""
    current_lines: list[str] = []

    def flush():
        nonlocal current_role, current_lines
        if not current_role:
            current_lines = []
            return
        text = "\n".join(current_lines).strip()
        current_lines = []
        if not text:
            current_role = ""
            return
        item = {"role": current_role, "content": text}
        prev = out[-1] if out else None
        if prev and prev["role"] == item["role"] and prev["content"] == item["content"]:
            current_role = ""
            return
        if prev and prev["role"] == "user" and item["role"] == "assistant" and prev["content"] == item["content"]:
            current_role = ""
            return
        out.append(item)
        current_role = ""

    for raw_line in raw.splitlines():
        line = str(raw_line or "")
        m = _ROLE_LINE_RE.match(line)
        if m:
            flush()
            role = str(m.group(1) or "").strip().lower()
            rest = _TS_RE.sub("", str(m.group(2) or "")).strip()
            current_role = role
            current_lines = [rest] if rest else []
            continue
        if current_role:
            current_lines.append(line)

    flush()
    return out


def _append_local_user_message(
    session_id: str,
    text: str,
    has_image: bool,
    project_name: str | None,
    task_id: str | None,
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

    target = base / sf
    if not target.exists():
        return

    raw_target = read_md(target)
    sid = _extract_header_value(raw_target, "NodeOps Session ID")
    if sid and sid != session_id:
        return

    content = str(text or "").strip()
    if not content and has_image:
        content = "[image]"
    if not content:
        return

    existing = _parse_session_messages(raw_target)
    if existing:
        last = existing[-1]
        if str(last.get("role")) == "user" and str(last.get("content") or "").strip() == content:
            return

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    append_md(target, f"[User] {ts}\n{content}\n\n")


def _extract_runtime_message_id(msg: dict) -> str:
    info = msg.get("info")
    if isinstance(info, dict):
        return str(info.get("id") or "").strip()
    return ""


def _extract_runtime_message_has_error(msg: dict) -> bool:
    info = msg.get("info")
    return isinstance(info, dict) and isinstance(info.get("error"), dict)


def _extract_runtime_message_has_step_finish(msg: dict) -> bool:
    parts = msg.get("parts", msg.get("content", []))
    if not isinstance(parts, list):
        return False
    for part in parts:
        if isinstance(part, dict) and str(part.get("type") or "").strip().lower() == "step-finish":
            return True
    return False


def _rewrite_session_messages_snapshot(raw: str, rows: list[dict]) -> str:
    marker = "## Messages"
    if marker in raw:
        idx = raw.find(marker)
        marker_end = raw.find("\n", idx)
        if marker_end == -1:
            header = raw.rstrip("\n") + "\n"
        else:
            header = raw[: marker_end + 1]
        if not header.endswith("\n\n"):
            header = header.rstrip("\n") + "\n\n"
    else:
        header = raw.rstrip("\n")
        if header:
            header += "\n\n"
        header += "## Messages\n\n"

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    body_lines: list[str] = []
    for row in rows:
        role = str(row.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = str(row.get("content") or "").strip()
        if not content:
            continue
        tag = "Assistant" if role == "assistant" else "User"
        body_lines.append(f"[{tag}] {ts}\n{content}\n\n")
    return header + "".join(body_lines)


async def _sync_session_file_once_from_runtime(
    path: Path,
    runtime_host: str,
    project_token: str,
    auth_token: str,
    session_id: str,
) -> int:
    if not path.exists():
        return 0
    sid = str(session_id or "").strip()
    if not sid:
        return 0

    remote = await noc.get_messages(runtime_host, project_token, auth_token, sid)
    remote_msgs = _normalize_runtime_messages(remote)
    if not remote_msgs:
        return 0

    raw = read_md(path)
    updated = _rewrite_session_messages_snapshot(raw, remote_msgs)
    if updated != raw:
        path.write_text(updated, encoding="utf-8")
    return len(remote_msgs)


async def _refresh_session_file_once_from_runtime(
    path: Path,
    project_name: str,
    task_id: str,
    account_id: str | None,
    current_content: str,
) -> list[dict] | None:
    task = task_engine.get_task(project_name, task_id) or {}
    runtime_host = str(task.get("current_runtime_host") or "").strip()
    project_token = str(task.get("current_project_token") or "").strip()

    aid = str(account_id or "").strip() or str(task.get("current_account_id") or "").strip()
    acc = account_pool.get_account(aid) if aid else None
    if not acc:
        for used_id in task.get("used_account_ids", []):
            candidate = account_pool.get_account(str(used_id or "").strip())
            if candidate and candidate.get("auth_token"):
                acc = candidate
                break
    if not acc:
        account_email = _extract_header_value(current_content, "Account") or ""
        if account_email:
            acc = account_pool.get_account_by_email(account_email)
    if not acc or not acc.get("auth_token"):
        return None

    auth_token = str(acc.get("auth_token") or "").strip()
    if not runtime_host:
        runtime_host = str(acc.get("runtime_host") or "").strip()
    if not project_token:
        project_token = str(acc.get("project_token") or "").strip()
    if not runtime_host or not project_token:
        return None

    session_id = _extract_header_value(current_content, "NodeOps Session ID") or ""
    session_id = str(session_id).strip()
    if not session_id:
        return None

    await _sync_session_file_once_from_runtime(
        path=path,
        runtime_host=runtime_host,
        project_token=project_token,
        auth_token=auth_token,
        session_id=session_id,
    )
    try:
        remote = await noc.get_messages(runtime_host, project_token, auth_token, session_id)
        return _normalize_runtime_messages(remote)
    except Exception:
        logger.debug(
            "fetch runtime messages for response failed: project=%s task=%s session_id=%s",
            project_name,
            task_id,
            session_id,
            exc_info=True,
        )
        return None


def _normalize_runtime_messages(messages_data: object) -> list[dict]:
    rows = normalize_messages(messages_data)
    out: list[dict] = []
    for msg in rows:
        role = normalize_chat_role(extract_message_role(msg))
        if role not in {"user", "assistant"}:
            continue
        content = extract_message_text(msg).strip()
        if not content:
            continue
        item = {"role": role, "content": content}
        prev = out[-1] if out else None
        if prev and prev["role"] == item["role"] and prev["content"] == item["content"]:
            continue
        if prev and prev["role"] == "user" and item["role"] == "assistant" and prev["content"] == item["content"]:
            continue
        out.append(item)
    return out


def _normalize_runtime_messages_meta(messages_data: object) -> list[dict]:
    rows = normalize_messages(messages_data)
    out: list[dict] = []
    for msg in rows:
        role = normalize_chat_role(extract_message_role(msg))
        if role not in {"user", "assistant"}:
            continue
        out.append({
            "id": _extract_runtime_message_id(msg),
            "role": role,
            "content": extract_message_text(msg).strip(),
            "has_step_finish": _extract_runtime_message_has_step_finish(msg),
            "has_error": _extract_runtime_message_has_error(msg),
        })
    return out


def _is_runtime_turn_complete(
    rows_meta: list[dict],
    sent_user_message_id: str | None,
    sent_user_text: str | None,
) -> bool:
    if not rows_meta:
        return False

    sid = str(sent_user_message_id or "").strip()
    stext = str(sent_user_text or "").strip()
    start_idx = -1

    if sid:
        for i, row in enumerate(rows_meta):
            if row.get("role") == "user" and str(row.get("id") or "").strip() == sid:
                start_idx = i

    if start_idx < 0 and stext:
        for i, row in enumerate(rows_meta):
            if row.get("role") == "user" and str(row.get("content") or "").strip() == stext:
                start_idx = i

    if start_idx < 0:
        # If we cannot locate the triggering user row, don't terminate early.
        return False

    for row in rows_meta[start_idx + 1:]:
        if row.get("has_error"):
            return True
        if row.get("role") == "assistant" and row.get("has_step_finish"):
            return True
    return False


def _extract_send_response_message_id(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    info = payload.get("info")
    if not isinstance(info, dict):
        return ""
    return str(info.get("id") or "").strip()


def _extract_credit_error_message(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    payload_type = str(payload.get("type") or "").strip().lower()
    if payload_type != "session.error":
        return ""
    props = payload.get("properties")
    if not isinstance(props, dict):
        return ""
    err = props.get("error")
    if not isinstance(err, dict):
        return ""
    return str(err.get("message") or "").strip()


async def _watch_credit_exhausted_sse(
    runtime_host: str,
    project_token: str,
    session_id: str,
    state: dict[str, object],
):
    """Background watcher for session SSE credit exhaustion signals."""
    async for _event_name, payload in parse_sse_payloads(
        noc.connect_sse(runtime_host, project_token, session_id)
    ):
        message = _extract_credit_error_message(payload)
        if _should_mark_account_exhausted(message):
            state["credit_exhausted"] = True
            state["message"] = message
            return


async def _sync_session_file_from_runtime(
    project_name: str,
    task_id: str,
    session_file: str,
    runtime_host: str,
    project_token: str,
    auth_token: str,
    account_id: str | None,
    session_id: str,
    sent_user_message_id: str | None = None,
    sent_user_text: str | None = None,
):
    from backend.storage.file_store import repo_dir

    base = repo_dir(project_name) / ".nodeops" / task_id
    path = base / str(session_file or "")
    if not path.exists():
        return
    sid = str(session_id or "").strip()
    if not sid:
        return

    try:
        poll_interval_s = max(
            1.0, float(os.environ.get("NODEOPS_SESSION_SYNC_POLL_INTERVAL_S", "5"))
        )
    except Exception:
        poll_interval_s = 5.0
    try:
        max_wait_s = max(
            poll_interval_s, float(os.environ.get("NODEOPS_SESSION_SYNC_MAX_SECONDS", "900"))
        )
    except Exception:
        max_wait_s = 900.0

    sse_state: dict[str, object] = {"credit_exhausted": False, "message": ""}
    sse_task = asyncio.create_task(
        _watch_credit_exhausted_sse(
            runtime_host=runtime_host,
            project_token=project_token,
            session_id=sid,
            state=sse_state,
        )
    )

    try:
        deadline = time.monotonic() + max_wait_s
        while time.monotonic() < deadline:
            try:
                if bool(sse_state.get("credit_exhausted")):
                    if account_id:
                        try:
                            account_pool.mark_account_status(str(account_id), "exhausted")
                        except Exception:
                            logger.exception(
                                "Failed to mark account exhausted from SSE watcher: account_id=%s",
                                account_id,
                            )
                    logger.info(
                        "Session sync stopped on SSE credit exhausted: project=%s task=%s file=%s session=%s msg=%s",
                        project_name,
                        task_id,
                        session_file,
                        sid,
                        str(sse_state.get("message") or ""),
                    )
                    return

                await _sync_session_file_once_from_runtime(
                    path=path,
                    runtime_host=runtime_host,
                    project_token=project_token,
                    auth_token=auth_token,
                    session_id=sid,
                )
                remote = await noc.get_messages(runtime_host, project_token, auth_token, sid)
                remote_meta = _normalize_runtime_messages_meta(remote)
                if any(
                    bool(row.get("has_error"))
                    and credit_monitor.is_credit_error(str(row.get("content") or ""))
                    for row in remote_meta
                ):
                    if account_id:
                        try:
                            account_pool.mark_account_status(str(account_id), "exhausted")
                        except Exception:
                            logger.exception(
                                "Failed to mark account exhausted from remote meta: account_id=%s",
                                account_id,
                            )
                    return

                if _is_runtime_turn_complete(
                    remote_meta,
                    sent_user_message_id=sent_user_message_id,
                    sent_user_text=sent_user_text,
                ):
                    return
            except Exception:
                logger.debug(
                    "session sync retry failed: project=%s task=%s file=%s session=%s",
                    project_name,
                    task_id,
                    session_file,
                    sid,
                    exc_info=True,
                )
            await asyncio.sleep(poll_interval_s)
    finally:
        if not sse_task.done():
            sse_task.cancel()
        try:
            await sse_task
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug(
                "session sync SSE watcher finished with error: project=%s task=%s session=%s",
                project_name,
                task_id,
                sid,
                exc_info=True,
            )

    logger.info(
        "Session sync timed out before completion marker: project=%s task=%s file=%s session=%s wait=%ss",
        project_name,
        task_id,
        session_file,
        sid,
        int(max_wait_s),
    )


async def _bootstrap_fresh_runtime_session_for_task_send(
    req: SendMessageRequest,
    account_id: str,
    account: dict,
    prompt_for_runtime: str,
    attempts: int = 3,
) -> tuple[str, str, str]:
    """
    Upstream-aligned bootstrap: deployment(prompt) → health → session → POST message.

    The deployment prompt automatically becomes the first user message in the
    session.  POST /session/{id}/message with the same text then triggers
    assistant inference (verified via capture 2026-05-10).
    """
    last_exc: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            # 1. Create deployment with user message as prompt
            runtime = await task_engine.ensure_task_runtime_for_send(
                req.project_name or "",
                req.task_id or "",
                account_id,
                prompt_for_runtime,
                force_new=True,
            )
            runtime_host = str(runtime.get("runtime_host") or "").strip()
            project_token = str(runtime.get("project_token") or "").strip()
            if not runtime_host or not project_token:
                raise RuntimeError("runtime/project token missing after deployment bootstrap")

            # 2. Create session (upstream passes model here too)
            created = await noc.create_session(
                runtime_host,
                project_token,
                account["auth_token"],
                title=req.project_name or req.task_id or "session",
                model=req.model.model_dump() if req.model else None,
            )
            created_session_id = (
                str(created.get("id") or "")
                or str(created.get("sessionId") or "")
                or str(created.get("session_id") or "")
            ).strip()
            if not created_session_id:
                raise RuntimeError(f"session created but id missing: {created}")

            # 3. Update task record & rewrite local .md header
            task_engine.update_task(req.project_name or "", req.task_id or "", {
                "current_account_id": account_id,
                "current_runtime_host": runtime_host,
                "current_project_token": project_token,
                "current_session_id": created_session_id,
            })
            _replace_local_session_id_header(
                req.project_name,
                req.task_id,
                req.session_file,
                created_session_id,
                account_email=str(account.get("email") or "").strip(),
            )
            return runtime_host, project_token, created_session_id
        except Exception as exc:
            last_exc = exc
            if attempt < attempts and _is_transient_upstream_error(str(exc)):
                wait_s = min(2 ** (attempt - 1), 4)
                logger.warning(
                    "Transient fresh runtime/session bootstrap failure (attempt %s/%s), retry in %ss: %s",
                    attempt,
                    attempts,
                    wait_s,
                    exc,
                )
                await asyncio.sleep(wait_s)
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("fresh runtime/session bootstrap failed")


def _replace_local_session_id_header(
    project_name: str | None,
    task_id: str | None,
    session_file: str | None,
    new_session_id: str,
    account_email: str | None = None,
):
    from backend.storage.file_store import repo_dir

    pn = str(project_name or "").strip()
    tid = str(task_id or "").strip()
    sf = str(session_file or "").strip()
    sid = str(new_session_id or "").strip()
    if not pn or not tid or not sf or not sid:
        return

    path = repo_dir(pn) / ".nodeops" / tid / sf
    if not path.exists():
        return

    raw = read_md(path)
    if not raw:
        return

    session_prefix = "- NodeOps Session ID:"
    account_prefix = "- Account:"
    next_account = str(account_email or "").strip()
    out_lines: list[str] = []
    replaced_session = False
    replaced_account = False
    for line in raw.splitlines():
        if line.startswith(session_prefix):
            out_lines.append(f"{session_prefix} {sid}")
            replaced_session = True
        elif next_account and line.startswith(account_prefix):
            out_lines.append(f"{account_prefix} {next_account}")
            replaced_account = True
        else:
            out_lines.append(line)
    if not replaced_session:
        return
    if next_account and not replaced_account:
        # Keep header compact: append account line right after title block when missing.
        inserted = False
        rewritten: list[str] = []
        for line in out_lines:
            rewritten.append(line)
            if not inserted and line.startswith(session_prefix):
                rewritten.insert(len(rewritten) - 1, f"{account_prefix} {next_account}")
                inserted = True
        out_lines = rewritten

    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


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
    return bool(credit_monitor.is_credit_error(str(message or "")))


def _is_transient_upstream_error(message: str) -> bool:
    msg = str(message or "").strip().lower()
    if not msg:
        return False
    transient_keywords = (
        "503",
        "service unavailable",
        "connection refused",
        "connect error",
        "upstream connect error",
        "remote connection failure",
        "transport failure",
        "delayed connect error",
        "timed out",
        "timeout",
        "reset before headers",
        "connection reset",
        "temporarily unavailable",
        "temporary failure",
        "health check failed",
        "/health",
    )
    if any(kw in msg for kw in transient_keywords):
        return True
    # Runtime may briefly return 404 for brand-new session propagation.
    if "404" in msg and "/session/" in msg:
        return True
    # Runtime may transiently return 403 on fresh deployment session creation
    # before token/route propagation settles.
    if "403" in msg and "/session" in msg and "orak.nodeops.app" in msg:
        return True
    return False
