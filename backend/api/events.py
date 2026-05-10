"""SSE event forwarding — subscribes to NodeOps SSE and relays to frontend."""
import asyncio
import json
import logging
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from backend.services import nodeops_client as noc
from backend.services import account_pool
from backend.services import task_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events", tags=["events"])


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
            # Use project_token as the SSE token (as per NodeOps API)
            async for line in noc.connect_sse(
                runtime_host, project_token, session_id
            ):
                if line:
                    yield f"{line}\n"
                else:
                    yield "\n"
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
