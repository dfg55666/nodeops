"""SSE event forwarding — subscribes to NodeOps SSE and relays to frontend."""
import asyncio
import json
import logging
from typing import Any
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from backend.services import nodeops_client as noc
from backend.services import account_pool
from backend.services import task_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["events"])


def _extract_message_role(msg: dict) -> str:
    role = msg.get("role")
    if role:
        return str(role).strip().lower()
    info = msg.get("info")
    if isinstance(info, dict):
        info_role = info.get("role")
        if info_role:
            return str(info_role).strip().lower()
    return "unknown"


def _normalize_chat_role(role: str) -> str:
    v = str(role or "").strip().lower()
    if v in {"user", "assistant"}:
        return v
    if v == "unknown":
        return "assistant"
    return v


def _extract_message_text(msg: dict) -> str:
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


def _semantic_session_event(
    session_id: str,
    event_name: str,
    payload: Any,
) -> tuple[str, dict[str, Any]] | None:
    if not isinstance(payload, dict):
        return None

    payload_type = str(payload.get("type") or "").strip().lower()
    props = payload.get("properties") if isinstance(payload.get("properties"), dict) else {}

    if payload_type == "session.status":
        status = ""
        status_obj = props.get("status")
        if isinstance(status_obj, dict):
            status = str(status_obj.get("type") or "").strip().lower()
        elif status_obj is not None:
            status = str(status_obj).strip().lower()
        if not status:
            return None
        return "status", {"session_id": session_id, "status": status}

    if payload_type == "session.error":
        err = props.get("error") if isinstance(props.get("error"), dict) else {}
        message = str(err.get("message") or "session error")
        status = err.get("status")
        out = {"session_id": session_id, "message": message}
        if status is not None:
            out["status"] = status
        return "error", out

    if payload_type == "message.part.updated":
        part = props.get("part") if isinstance(props.get("part"), dict) else {}
        part_type = str(part.get("type") or "").strip().lower()
        if part_type != "text":
            return None
        text = str(part.get("text") or "").strip()
        if not text:
            return None
        return "message_part", {
            "session_id": session_id,
            "role": "assistant",
            "content": text,
        }

    msg_obj = None
    if payload_type in {"message.updated", "message.completed"}:
        candidate = props.get("message")
        if isinstance(candidate, dict):
            msg_obj = candidate
    if msg_obj is None and isinstance(payload.get("message"), dict):
        msg_obj = payload.get("message")
    if msg_obj is None and isinstance(payload.get("data"), dict):
        msg_obj = payload.get("data")
    if msg_obj is None:
        msg_obj = payload

    role = _normalize_chat_role(_extract_message_role(msg_obj))
    text = _extract_message_text(msg_obj).strip()
    if role not in {"user", "assistant"} or not text:
        return None
    return "message", {
        "session_id": session_id,
        "role": role,
        "content": text,
    }


@router.get("/session/{session_id}")
async def stream_session_events(
    session_id: str,
    account_id: str | None = Query(None),
    project_name: str | None = Query(None),
    task_id: str | None = Query(None),
):
    """SSE stream: forward NodeOps session events to frontend.

    Supports:
    - account_id + session_id
    - task_id (+ optional project_name) + session_id
    """
    runtime_host = ""
    project_token = ""
    source = {}

    if account_id:
        source = account_pool.get_account(account_id) or {}
        if not source:
            raise HTTPException(404, "Account not found")
        runtime_host = str(source.get("runtime_host") or "").strip()
        project_token = str(source.get("project_token") or "").strip()
    elif task_id:
        task = None
        if project_name:
            task = task_engine.get_task(project_name, task_id)
        else:
            for candidate in task_engine.list_all_tasks():
                if str(candidate.get("id")) == task_id:
                    task = candidate
                    break
        if not task:
            raise HTTPException(404, "Task not found")
        acc_id = str(task.get("current_account_id") or "")
        if not acc_id:
            raise HTTPException(400, "Task has no active account")
        source = account_pool.get_account(acc_id) or {}
        if not source:
            raise HTTPException(404, "Task account not found")
        runtime_host = str(task.get("current_runtime_host") or source.get("runtime_host") or "").strip()
        project_token = str(task.get("current_project_token") or source.get("project_token") or "").strip()
    else:
        raise HTTPException(400, "account_id or task_id is required")

    if not runtime_host or not project_token:
        raise HTTPException(400, "No active runtime/deployment info")

    async def event_generator():
        try:
            # Parse upstream SSE then emit semantic events only.
            upstream_event = "message"
            data_lines: list[str] = []

            async def flush_event() -> str | None:
                nonlocal upstream_event, data_lines
                if not data_lines:
                    upstream_event = "message"
                    return None
                data_text = "\n".join(data_lines)
                data_lines = []
                payload: Any = data_text
                try:
                    payload = json.loads(data_text)
                except Exception:
                    upstream_event = "message"
                    return None
                mapped = _semantic_session_event(session_id, upstream_event, payload)
                upstream_event = "message"
                if not mapped:
                    return None
                mapped_event, mapped_payload = mapped
                return (
                    f"event: {mapped_event}\n"
                    f"data: {json.dumps(mapped_payload, default=str, ensure_ascii=False)}\n\n"
                )

            async for line in noc.connect_sse(
                runtime_host, project_token, session_id
            ):
                if line is None:
                    continue
                line = str(line)
                if line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    upstream_event = line.split(":", 1)[1].strip() or "message"
                    continue
                if line.startswith("data:"):
                    data_lines.append(line.split(":", 1)[1].lstrip())
                    continue
                if line.strip() == "":
                    out = await flush_event()
                    if out:
                        yield out
                    continue
                data_lines.append(line)

            out = await flush_event()
            if out:
                yield out
        except Exception as e:
            logger.error(f"SSE stream error: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/task/{project_name}/{task_id}")
async def stream_task_events(project_name: str, task_id: str):
    """SSE stream: forward buffered task events + status updates."""

    async def event_generator():
        last_seq = 0
        last_status = None
        heartbeat_count = 0
        while True:
            task = task_engine.get_task(project_name, task_id)
            if not task:
                yield f"event: error\ndata: {json.dumps({'error': 'Task not found'})}\n\n"
                break

            # Emit status when changed
            if task.get("status") != last_status:
                last_status = task.get("status")
                status_payload = {
                    "status": task.get("status"),
                    "loop_count": task.get("loop_count", 0),
                    "max_loops": task.get("max_loops", 0),
                }
                yield f"event: status\ndata: {json.dumps(status_payload, default=str)}\n\n"

            # Emit buffered task events
            events, cursor = task_engine.get_task_events(task_id, after_seq=last_seq)
            if events:
                for ev in events:
                    ev_type = str(ev.get("type") or "event")
                    yield f"event: {ev_type}\ndata: {json.dumps(ev, default=str)}\n\n"
                last_seq = cursor
                heartbeat_count = 0
            else:
                heartbeat_count += 1
                if heartbeat_count >= 10:
                    heartbeat_count = 0
                    yield ": ping\n\n"

            # Stop if task is done
            if task["status"] in ("completed", "failed", "canceled", "stopped", "blocked", "blocked_no_account"):
                yield f"event: done\ndata: {json.dumps({'status': task['status']})}\n\n"
                break

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
