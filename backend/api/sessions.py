"""Session & message proxy routes — direct access to NodeOps runtime."""
import asyncio
from datetime import datetime, timezone
import logging
import os
import re
import time
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from backend.services import nodeops_client as noc
from backend.services import account_pool
from backend.services import task_engine
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
    if task_bound_send:
        task_state = task_engine.get_task(str(req.project_name or ""), str(req.task_id or ""))
        if isinstance(task_state, dict):
            runtime_host = str(task_state.get("current_runtime_host") or runtime_host).strip()
            project_token = str(task_state.get("current_project_token") or project_token).strip()

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
        "Session send request: session_id=%s account_id=%s account_email=%s text_len=%s has_image=%s model=%s",
        session_id,
        account_id,
        acc.get("email"),
        len(str(req.text or "")),
        bool(str(req.image_url or "").strip()),
        requested_model or "<session-default>",
    )

    data = None
    send_attempts = 3
    for send_attempt in range(1, send_attempts + 1):
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
def get_session_content(project_name: str, task_id: str,
                        session_file: str = Query(...)):
    """Read the content of a session .md file."""
    from backend.storage.file_store import repo_dir
    base = repo_dir(project_name) / ".nodeops" / task_id
    path = base / session_file
    if not path.exists():
        raise HTTPException(404, "Session file not found")
    content = read_md(path)
    messages = _parse_session_messages(content)
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


def _extract_runtime_message_role(msg: dict) -> str:
    role = msg.get("role")
    if role:
        return str(role).strip().lower()
    info = msg.get("info")
    if isinstance(info, dict):
        info_role = info.get("role")
        if info_role:
            return str(info_role).strip().lower()
    return "unknown"


def _extract_runtime_message_text(msg: dict) -> str:
    if isinstance(msg.get("content"), str):
        return str(msg.get("content") or "")
    parts = msg.get("parts", msg.get("content", []))
    if isinstance(parts, list):
        texts: list[str] = []
        for part in parts:
            if isinstance(part, dict) and str(part.get("type") or "") == "text":
                texts.append(str(part.get("text") or ""))
            elif isinstance(part, str):
                texts.append(part)
        joined = "\n".join([t for t in texts if str(t).strip()])
        if joined.strip():
            return joined
    return str(msg.get("text") or "")


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


def _extract_runtime_message_objects(messages_data: object) -> list[dict]:
    if isinstance(messages_data, list):
        return [m for m in messages_data if isinstance(m, dict)]
    if isinstance(messages_data, dict):
        raw = (
            messages_data.get("messages")
            or messages_data.get("items")
            or messages_data.get("data")
            or []
        )
        if isinstance(raw, list):
            return [m for m in raw if isinstance(m, dict)]
    return []


def _normalize_runtime_messages(messages_data: object) -> list[dict]:
    rows = _extract_runtime_message_objects(messages_data)
    out: list[dict] = []
    for msg in rows:
        role = _extract_runtime_message_role(msg)
        if role == "unknown":
            role = "assistant"
        if role not in {"user", "assistant"}:
            continue
        content = _extract_runtime_message_text(msg).strip()
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
    rows = _extract_runtime_message_objects(messages_data)
    out: list[dict] = []
    for msg in rows:
        role = _extract_runtime_message_role(msg)
        if role == "unknown":
            role = "assistant"
        if role not in {"user", "assistant"}:
            continue
        out.append({
            "id": _extract_runtime_message_id(msg),
            "role": role,
            "content": _extract_runtime_message_text(msg).strip(),
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


async def _sync_session_file_from_runtime(
    project_name: str,
    task_id: str,
    session_file: str,
    runtime_host: str,
    project_token: str,
    auth_token: str,
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

    deadline = time.monotonic() + max_wait_s
    while time.monotonic() < deadline:
        try:
            remote = await noc.get_messages(runtime_host, project_token, auth_token, sid)
            remote_msgs = _normalize_runtime_messages(remote)
            remote_meta = _normalize_runtime_messages_meta(remote)
            raw = read_md(path)
            local_msgs = _parse_session_messages(raw)

            start = 0
            if local_msgs:
                last = local_msgs[-1]
                matched = False
                for idx in range(len(remote_msgs) - 1, -1, -1):
                    if (
                        remote_msgs[idx]["role"] == last["role"]
                        and remote_msgs[idx]["content"].strip() == str(last.get("content") or "").strip()
                    ):
                        start = idx + 1
                        matched = True
                        break
                if not matched:
                    prefix = 0
                    while (
                        prefix < len(local_msgs)
                        and prefix < len(remote_msgs)
                        and local_msgs[prefix]["role"] == remote_msgs[prefix]["role"]
                        and str(local_msgs[prefix].get("content") or "").strip() == remote_msgs[prefix]["content"].strip()
                    ):
                        prefix += 1
                    start = prefix

            new_rows = remote_msgs[start:]
            if new_rows:
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                chunks: list[str] = []
                for row in new_rows:
                    tag = "Assistant" if row["role"] == "assistant" else "User"
                    chunks.append(f"[{tag}] {ts}\n{row['content']}\n\n")
                append_md(path, "".join(chunks))

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

    prefix = "- NodeOps Session ID:"
    out_lines: list[str] = []
    replaced = False
    for line in raw.splitlines():
        if line.startswith(prefix):
            out_lines.append(f"{prefix} {sid}")
            replaced = True
        else:
            out_lines.append(line)
    if not replaced:
        return

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
