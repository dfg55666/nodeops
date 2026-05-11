"""
Task engine — the core loop system.

Manages task lifecycle:
  pending → running → monitoring → completed / switching / blocked

Auto mode: credit exhausted → sync workspace → git push → switch account → new session → resend message
Oneshot mode: credit exhausted → blocked
"""
import asyncio
import json
import os
import uuid
import logging
import time
import shutil
from pathlib import Path
from typing import Any
from backend.storage.file_store import (
    task_json, tasks_dir, project_json, read_json, write_json, now_iso, repo_dir, session_md_path,
)
from backend.services import nodeops_client as noc
from backend.services import account_pool
from backend.services import workspace_sync
from backend.services import session_recorder
from backend.services import credit_monitor
from backend.services.message_utils import (
    extract_message_role as _extract_message_role,
    extract_message_text as _extract_message_text,
    normalize_chat_role as _normalize_chat_role,
    normalize_messages as _normalize_messages,
)
from backend.services.register import (
    GmailConfig,
    RegisterConfig,
    generate_gmail_aliases,
    gmail_auto_register,
)
from backend.services.sse_parser import parse_sse_payloads

logger = logging.getLogger(__name__)

# Active task loops (task_id -> asyncio.Task)
_active_tasks: dict[str, asyncio.Task] = {}

# Message cache for active sessions: task_id -> list of message dicts
_message_cache: dict[str, list[dict]] = {}

# Task event cache for SSE forwarding: task_id -> [{seq,type,data,at}]
_task_events: dict[str, list[dict[str, Any]]] = {}
_task_event_seq: dict[str, int] = {}

# SSE stop events: task_id -> asyncio.Event
_stop_events: dict[str, asyncio.Event] = {}
_EVENT_BUFFER_LIMIT = 500


# ─── Task CRUD ──────────────────────────────────────────────────────

def _normalize_model_ref(model: Any) -> dict[str, str] | None:
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
            raise ValueError("model.modelID is required")
        return {"providerID": provider_id, "modelID": model_id}
    raise ValueError("model must be an object with providerID/modelID")


def create_task(project_name: str, mode: str, message: str,
                commit_prompt: str | None = None,
                fallback_sync: bool = True,
                model: dict | None = None,
                max_loops: int = 10, task_id: str | None = None) -> dict:
    """Create a new task definition."""
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode not in ("auto", "oneshot"):
        raise ValueError("mode must be one of: auto | oneshot")
    if not str(message or "").strip():
        raise ValueError("message cannot be empty")
    if int(max_loops) <= 0:
        raise ValueError("max_loops must be > 0")
    normalized_model = _normalize_model_ref(model)
    normalized_commit_prompt = str(commit_prompt or "").strip() or None

    tid = task_id or f"task-{str(uuid.uuid4())[:8]}"

    # Ensure project exists
    pj = project_json(project_name)
    if not pj.exists():
        raise ValueError(f"Project '{project_name}' does not exist")

    task = {
        "id": tid,
        "project": project_name,
        "mode": normalized_mode,
        "status": "pending",
        "message": message,
        "commit_prompt": normalized_commit_prompt,
        "fallback_sync": bool(fallback_sync),
        "model": normalized_model,
        "current_account_id": None,
        "current_session_id": None,
        "current_runtime_host": None,
        "current_project_token": None,
        "loop_count": 0,
        "max_loops": max_loops,
        "session_index": 0,
        "used_account_ids": [],
        "loops": [],
        "error": None,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }

    path = task_json(project_name, tid)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, task)
    logger.info(f"Created task {tid} in project {project_name}")
    return task


def get_task(project_name: str, task_id: str) -> dict | None:
    path = task_json(project_name, task_id)
    if not path.exists():
        return None
    return read_json(path)


def update_task(project_name: str, task_id: str, updates: dict) -> dict | None:
    task = get_task(project_name, task_id)
    if not task:
        return None
    if "model" in updates:
        updates["model"] = _normalize_model_ref(updates.get("model"))
    if "commit_prompt" in updates:
        updates["commit_prompt"] = str(updates.get("commit_prompt") or "").strip() or None
    if "fallback_sync" in updates:
        updates["fallback_sync"] = bool(updates.get("fallback_sync"))
    prev_status = task.get("status")
    prev_error = task.get("error")
    task.update(updates)
    task["updated_at"] = now_iso()
    write_json(task_json(project_name, task_id), task)

    if task.get("status") != prev_status:
        _emit_task_event(task_id, "status", {
            "status": task.get("status"),
            "project": project_name,
            "task_id": task_id,
            "loop_count": task.get("loop_count", 0),
        })
    if task.get("error") and task.get("error") != prev_error:
        _emit_task_event(task_id, "error", {
            "project": project_name,
            "task_id": task_id,
            "error": task.get("error"),
        })
    return task


def list_tasks(project_name: str) -> list[dict]:
    tdir = tasks_dir(project_name)
    if not tdir.exists():
        return []
    tasks = []
    for f in tdir.glob("*.json"):
        tasks.append(read_json(f))
    return sorted(tasks, key=lambda t: t.get("created_at", ""))


def list_all_tasks() -> list[dict]:
    """List tasks across all projects."""
    from backend.storage.file_store import DATA_DIR
    projects_dir = DATA_DIR / "projects"
    if not projects_dir.exists():
        return []
    all_tasks = []
    for pdir in projects_dir.iterdir():
        if pdir.is_dir():
            all_tasks.extend(list_tasks(pdir.name))
    return all_tasks


def delete_task(project_name: str, task_id: str) -> bool:
    path = task_json(project_name, task_id)
    if not path.exists():
        return False

    task = read_json(path) or {}

    # Best-effort stop active loop and clear in-memory buffers.
    if task_id in _stop_events:
        _stop_events[task_id].set()
    active = _active_tasks.pop(task_id, None)
    if active and not active.done():
        active.cancel()

    _message_cache.pop(task_id, None)
    _task_events.pop(task_id, None)
    _task_event_seq.pop(task_id, None)
    _stop_events.pop(task_id, None)

    # Release account lock if this task still holds one.
    current_account_id = str(task.get("current_account_id") or "").strip()
    if current_account_id:
        try:
            account_pool.release_account(current_account_id)
        except Exception:
            logger.warning("Failed to release account when deleting task %s", task_id)

    # Remove persisted session history to avoid same task_id reusing old sessions.
    sessions_dir = repo_dir(project_name) / ".nodeops" / task_id
    if sessions_dir.exists():
        shutil.rmtree(sessions_dir, ignore_errors=True)

    path.unlink()
    return True


# ─── Task Execution ─────────────────────────────────────────────────

async def start_task(project_name: str, task_id: str):
    """Start the task loop in the background."""
    task = get_task(project_name, task_id)
    if not task:
        raise ValueError(f"Task {task_id} not found")

    if task_id in _active_tasks and not _active_tasks[task_id].done():
        raise ValueError(f"Task {task_id} is already running")

    _stop_events[task_id] = asyncio.Event()
    _message_cache[task_id] = []
    _task_events[task_id] = []
    _task_event_seq[task_id] = 0

    async_task = asyncio.create_task(_task_loop(project_name, task_id))
    _active_tasks[task_id] = async_task
    _emit_task_event(task_id, "task_started", {
        "project": project_name,
        "task_id": task_id,
    })
    logger.info(f"Started task loop: {task_id}")


async def cancel_task(project_name: str, task_id: str):
    """Cancel a running task."""
    if task_id in _stop_events:
        _stop_events[task_id].set()

    if task_id in _active_tasks:
        _active_tasks[task_id].cancel()
        del _active_tasks[task_id]

    task = get_task(project_name, task_id)
    if task and task["status"] not in ("completed", "failed", "canceled"):
        # Release account if locked
        if task.get("current_account_id"):
            account_pool.release_account(task["current_account_id"])
        update_task(project_name, task_id, {"status": "canceled"})
    _emit_task_event(task_id, "task_canceled", {
        "project": project_name,
        "task_id": task_id,
    })
    logger.info(f"Canceled task: {task_id}")


def get_task_messages(task_id: str) -> list[dict]:
    """Get normalized chat messages for an active task."""
    cached = _message_cache.get(task_id, [])
    if not isinstance(cached, list):
        return []

    out: list[dict] = []
    for msg in cached:
        if not isinstance(msg, dict):
            continue
        role = _normalize_chat_role(_extract_message_role(msg))
        content = _extract_message_text(msg).strip()
        if not content:
            continue
        if role not in {"user", "assistant"}:
            continue
        item = {"role": role, "content": content}
        prev = out[-1] if out else None
        if prev and prev["role"] == item["role"] and prev["content"] == item["content"]:
            continue
        if prev and prev["role"] == "user" and item["role"] == "assistant" and prev["content"] == item["content"]:
            continue
        out.append(item)
    return out


def is_task_running(task_id: str) -> bool:
    return task_id in _active_tasks and not _active_tasks[task_id].done()


async def create_empty_session(project_name: str, task_id: str) -> dict:
    """Create an empty local session for a task without touching upstream runtime."""
    task = get_task(project_name, task_id)
    if not task:
        raise ValueError(f"Task {task_id} not found")

    active_statuses = {
        "running", "monitoring", "pending", "switching",
        "syncing", "pushing", "acquiring_account", "auto_registering_account",
        "bootstrapping_runtime", "creating_session", "sending_message", "submitting_commit",
    }
    if str(task.get("status") or "").lower() in active_statuses and is_task_running(task_id):
        raise ValueError("Task is running; stop it before creating a manual session")

    account: dict | None = None
    current_account_id = str(task.get("current_account_id") or "").strip()
    if current_account_id:
        account = account_pool.get_account(current_account_id)

    if not account:
        account = account_pool.acquire_account(
            exclude_ids=task.get("used_account_ids", []),
            task_id=task_id,
        )

    if not account:
        auto_reg_enabled = str(
            os.environ.get("NODEOPS_TASK_AUTO_REGISTER_ON_NO_ACCOUNT", "true")
        ).strip().lower() not in {"0", "false", "no", "off"}
        if auto_reg_enabled:
            await _auto_register_one_account(task_id)
            account = account_pool.acquire_account(
                exclude_ids=task.get("used_account_ids", []),
                task_id=task_id,
            )

    if not account:
        raise ValueError("No available accounts")

    locked_by = account.get("locked_by_task")
    if locked_by and locked_by != task_id:
        raise ValueError(f"Account is locked by another task: {locked_by}")
    if not locked_by:
        account = account_pool.update_account(account["id"], {
            "locked_by_task": task_id,
            "last_used_at": now_iso(),
        }) or account

    next_session_index = int(task.get("session_index", 0)) + 1
    session_id = f"local-{task_id}-{next_session_index}"

    used_ids = list(task.get("used_account_ids", []))
    if account["id"] not in used_ids:
        used_ids.append(account["id"])

    update_task(project_name, task_id, {
        "current_account_id": account["id"],
        # Empty local session does not create upstream deployment/session.
        "current_runtime_host": None,
        "current_project_token": None,
        "current_session_id": session_id,
        "session_index": next_session_index,
        "used_account_ids": used_ids,
        "error": None,
    })

    session_recorder.init_session_file(
        project_name, task_id, account["email"], next_session_index, session_id
    )

    _emit_task_event(task_id, "session_created", {
        "project": project_name,
        "task_id": task_id,
        "session_id": session_id,
        "session_index": next_session_index,
        "account_id": account["id"],
        "account_email": account["email"],
        "manual": True,
    })

    logger.info(
        "Task %s created local empty session %s using account %s",
        task_id, session_id, account["email"],
    )
    return {
        "project": project_name,
        "task_id": task_id,
        "session_id": session_id,
        "session_index": next_session_index,
        "session_file": f"session-{next_session_index}.md",
        "account_id": account["id"],
        "account_email": account["email"],
    }


async def switch_task_account(project_name: str, task_id: str) -> dict:
    """Switch the task to a new account (auto-selected by pool).

    Releases the current account and acquires a fresh one.
    Does NOT create a new session — the next send will bootstrap one.
    """
    task = get_task(project_name, task_id)
    if not task:
        raise ValueError(f"Task {task_id} not found")

    active_statuses = {
        "running", "monitoring", "pending", "switching",
        "syncing", "pushing", "acquiring_account", "auto_registering_account",
        "bootstrapping_runtime", "creating_session", "sending_message", "submitting_commit",
    }
    if str(task.get("status") or "").lower() in active_statuses and is_task_running(task_id):
        raise ValueError("Task is running; stop it before switching account")

    # Clean up any stale locks previously left on this task.
    account_pool.release_task_locks(task_id)

    # Release current account
    old_account_id = str(task.get("current_account_id") or "").strip()
    if old_account_id:
        account_pool.release_account(old_account_id)

    # Acquire new account (exclude used ones)
    exclude_ids = list(task.get("used_account_ids", []))
    account = account_pool.acquire_account(exclude_ids=exclude_ids, task_id=task_id)

    if not account:
        # Try auto-register
        auto_reg_enabled = str(
            os.environ.get("NODEOPS_TASK_AUTO_REGISTER_ON_NO_ACCOUNT", "true")
        ).strip().lower() not in {"0", "false", "no", "off"}
        if auto_reg_enabled:
            await _auto_register_one_account(task_id)
            account = account_pool.acquire_account(exclude_ids=exclude_ids, task_id=task_id)

    if not account:
        raise ValueError("No available accounts")

    # Keep only the new account lock for this task.
    account_pool.release_task_locks(task_id, keep_account_id=account["id"])

    used_ids = list(task.get("used_account_ids", []))
    if account["id"] not in used_ids:
        used_ids.append(account["id"])

    update_task(project_name, task_id, {
        "current_account_id": account["id"],
        "current_runtime_host": None,
        "current_project_token": None,
        # Account switch invalidates the previous upstream session binding.
        # Next send will bootstrap a fresh deployment/session.
        "current_session_id": None,
        "used_account_ids": used_ids,
        "error": None,
    })

    _emit_task_event(task_id, "account_switched", {
        "project": project_name,
        "task_id": task_id,
        "account_id": account["id"],
        "account_email": account["email"],
    })

    logger.info(
        "Task %s switched account: old=%s new=%s (%s)",
        task_id, old_account_id or "(none)", account["id"], account["email"],
    )
    return {
        "account_id": account["id"],
        "account_email": account["email"],
    }


def get_task_events(task_id: str, after_seq: int = 0) -> tuple[list[dict], int]:
    """Read buffered task events after sequence number."""
    events = _task_events.get(task_id, [])
    if not events:
        return [], _task_event_seq.get(task_id, 0)
    filtered = [ev for ev in events if int(ev.get("seq", 0)) > int(after_seq)]
    return filtered, _task_event_seq.get(task_id, 0)


# ─── Main Task Loop ─────────────────────────────────────────────────

async def _task_loop(project_name: str, task_id: str):
    """Main loop: acquire account → create session → send message → monitor → handle result."""
    try:
        task = get_task(project_name, task_id)
        update_task(project_name, task_id, {"status": "running"})

        while True:
            task = get_task(project_name, task_id)
            if not task:
                break

            if int(task.get("loop_count", 0)) >= int(task.get("max_loops", 10)):
                update_task(project_name, task_id, {
                    "status": "stopped",
                    "error": f"Reached max loops ({task['max_loops']})"
                })
                break

            if _stop_events.get(task_id, asyncio.Event()).is_set():
                break

            # ── Step 1: Acquire account ──
            update_task(project_name, task_id, {"status": "acquiring_account"})
            account = account_pool.acquire_account(
                exclude_ids=task.get("used_account_ids", []),
                task_id=task_id,
            )
            if not account:
                auto_reg_enabled = str(
                    os.environ.get("NODEOPS_TASK_AUTO_REGISTER_ON_NO_ACCOUNT", "true")
                ).strip().lower() not in {"0", "false", "no", "off"}
                if auto_reg_enabled:
                    update_task(project_name, task_id, {
                        "status": "auto_registering_account",
                        "error": None,
                    })
                    registered = await _auto_register_one_account(task_id)
                    if registered:
                        account = account_pool.acquire_account(
                            exclude_ids=task.get("used_account_ids", []),
                            task_id=task_id,
                        )

            if not account:
                update_task(project_name, task_id, {
                    "status": "blocked_no_account",
                    "error": "No available accounts"
                })
                logger.warning(f"Task {task_id}: no available accounts")
                break

            update_task(project_name, task_id, {
                "current_account_id": account["id"],
                "status": "bootstrapping_runtime",
                "error": None,
            })

            # ── Step 2: Ensure deployment ──
            try:
                deployment_info = await ensure_task_runtime_for_send(
                    project_name,
                    task_id,
                    account["id"],
                    prompt=str(task.get("message") or "").strip(),
                    force_new=True,
                )
                runtime_host = deployment_info["runtime_host"]
                project_token = deployment_info["project_token"]
            except Exception as e:
                logger.error(f"Task {task_id}: deployment failed: {e}")
                account_pool.release_account(account["id"])
                update_task(project_name, task_id, {
                    "status": "failed",
                    "error": f"Deployment failed: {e}"
                })
                break

            # ── Step 3: Create session ──
            try:
                update_task(project_name, task_id, {"status": "creating_session"})
                loop_index = int(task.get("loop_count", 0)) + 1
                session_data = await noc.create_session(
                    runtime_host, project_token, account["auth_token"],
                    title=f"{task_id} loop-{loop_index}"
                )
                session_id = (
                    str(session_data.get("id") or "")
                    or str(session_data.get("sessionId") or "")
                    or str(session_data.get("session_id") or "")
                ).strip()
                if not session_id:
                    raise RuntimeError(f"session created but id missing: {session_data}")
                task["session_index"] = task.get("session_index", 0) + 1
                update_task(project_name, task_id, {
                    "current_session_id": session_id,
                    "session_index": task["session_index"],
                    "status": "running",
                })
                _emit_task_event(task_id, "session_created", {
                    "project": project_name,
                    "task_id": task_id,
                    "session_id": session_id,
                    "session_index": task["session_index"],
                    "account_id": account["id"],
                    "account_email": account["email"],
                })
            except Exception as e:
                logger.error(f"Task {task_id}: create session failed: {e}")
                account_pool.release_account(account["id"])
                update_task(project_name, task_id, {
                    "status": "failed",
                    "error": f"Create session failed: {e}"
                })
                break

            # Init session recorder
            session_recorder.init_session_file(
                project_name, task_id, account["email"],
                task["session_index"], session_id
            )

            # ── Step 4: Send message ──
            try:
                update_task(project_name, task_id, {"status": "sending_message"})
                await noc.send_message(
                    runtime_host, project_token, account["auth_token"],
                    session_id, task["message"],
                    model=task.get("model"),
                )
                session_recorder.append_message(
                    project_name, task_id, account["email"],
                    task["session_index"], "User", task["message"]
                )
                _emit_task_event(task_id, "message", {
                    "role": "user",
                    "content": task["message"],
                    "session_id": session_id,
                    "session_index": task["session_index"],
                })
            except Exception as e:
                if credit_monitor.is_credit_error(str(e)):
                    logger.info(f"Task {task_id}: credit exhausted on send")
                    # Handle as credit exhausted
                    end_reason = await _handle_credit_exhausted(
                        project_name, task_id, task, account
                    )
                    if end_reason == "continue":
                        continue
                    break
                else:
                    logger.error(f"Task {task_id}: send message failed: {e}")
                    account_pool.release_account(account["id"])
                    update_task(project_name, task_id, {
                        "status": "failed",
                        "error": f"Send message failed: {e}"
                    })
                    break

            # ── Step 5: Monitor session ──
            update_task(project_name, task_id, {"status": "monitoring"})
            end_reason = await _monitor_session(
                project_name, task_id, task, account,
                runtime_host, project_token, session_id
            )

            if end_reason == "completed":
                # Task completed normally
                commit_hash = await _sync_and_push(project_name, task_id, task, account, "completed")
                session_recorder.finalize_session(
                    project_name, task_id, account["email"],
                    task["session_index"], "completed"
                )

                loops = task.get("loops", [])
                loops.append({
                    "index": int(task.get("loop_count", 0)) + 1,
                    "account_email": account["email"],
                    "session_id": task.get("current_session_id"),
                    "started_at": task.get("updated_at"),
                    "ended_at": now_iso(),
                    "end_reason": "completed",
                    "git_commit": commit_hash,
                })

                account_pool.release_account(account["id"])
                update_task(project_name, task_id, {
                    "status": "completed",
                    "loop_count": int(task.get("loop_count", 0)) + 1,
                    "loops": loops,
                    "current_account_id": None,
                    "current_session_id": None,
                })
                break

            elif end_reason == "credit_exhausted":
                result = await _handle_credit_exhausted(
                    project_name, task_id, task, account
                )
                if result == "continue":
                    continue
                break

            elif end_reason == "stuck_idle":
                result = await _handle_stuck_idle(
                    project_name, task_id, task, account
                )
                if result == "continue":
                    continue
                break

            elif end_reason == "error":
                account_pool.release_account(account["id"])
                break

            elif end_reason == "canceled":
                account_pool.release_account(account["id"])
                break

    except asyncio.CancelledError:
        logger.info(f"Task {task_id} was canceled")
        _release_task_account_lock(project_name, task_id)
        update_task(project_name, task_id, {
            "status": "canceled",
            "current_account_id": None,
            "current_session_id": None,
        })
    except Exception as e:
        logger.error(f"Task {task_id} unexpected error: {e}", exc_info=True)
        update_task(project_name, task_id, {
            "status": "failed",
            "error": str(e),
        })
    finally:
        _release_task_account_lock(project_name, task_id)
        _active_tasks.pop(task_id, None)
        _stop_events.pop(task_id, None)


# ─── Helpers ─────────────────────────────────────────────────────────

async def ensure_task_runtime_for_send(
    project_name: str,
    task_id: str,
    account_id: str,
    prompt: str | None = None,
    force_new: bool = False,
) -> dict:
    """
    Ensure task runtime exists for an outbound message.
    If task has no runtime context, create a fresh deployment with prompt.
    """
    task = get_task(project_name, task_id)
    if not task:
        raise ValueError("Task not found")

    account = account_pool.get_account(account_id)
    if not account:
        raise ValueError("Account not found")

    runtime_host = str(task.get("current_runtime_host") or "").strip()
    project_token = str(task.get("current_project_token") or "").strip()
    if runtime_host and project_token and not force_new:
        return {"runtime_host": runtime_host, "project_token": project_token}

    dep = await _ensure_deployment(account, prompt=prompt)
    runtime_host = dep["runtime_host"]
    project_token = dep["project_token"]
    update_task(project_name, task_id, {
        "current_account_id": account_id,
        "current_runtime_host": runtime_host,
        "current_project_token": project_token,
    })
    return {"runtime_host": runtime_host, "project_token": project_token}


async def _wait_runtime_healthy(
    runtime_host: str,
    project_token: str,
    auth_token: str,
    timeout: float = 30.0,
    interval: float = 1.5,
) -> bool:
    """Poll GET /health until {"ok":true} or timeout."""
    import time as _time
    req_timeout_s = float(os.environ.get("NODEOPS_RUNTIME_HEALTH_REQUEST_TIMEOUT_S", "4"))
    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        try:
            data = await noc.get_health(
                runtime_host,
                project_token=project_token,
                auth_token=auth_token,
                retries=1,
                timeout_s=req_timeout_s,
            )
            if isinstance(data, dict) and data.get("ok"):
                return True
        except Exception:
            pass
        await asyncio.sleep(interval)
    logger.warning("Runtime %s did not become healthy within %ss", runtime_host, timeout)
    return False


def _health_wait_enabled() -> bool:
    return str(os.environ.get("NODEOPS_RUNTIME_WAIT_HEALTH", "true")).strip().lower() in {
        "1", "true", "yes", "on",
    }


def _health_wait_seconds() -> float:
    try:
        return max(0.0, float(os.environ.get("NODEOPS_RUNTIME_HEALTH_WAIT_SECONDS", "30")))
    except Exception:
        return 30.0


def _health_poll_seconds() -> float:
    try:
        return max(0.2, float(os.environ.get("NODEOPS_RUNTIME_HEALTH_POLL_SECONDS", "1.5")))
    except Exception:
        return 1.5


async def _ensure_deployment(account: dict, prompt: str | None = None) -> dict:
    """
    Create a fresh deployment for this session.
    Returns {runtime_host, project_token}.
    """
    auth_token = account["auth_token"]
    create_prompt = str(prompt or "").strip() or "init"

    def _pick_runtime_host(detail: dict) -> str:
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

    def _pick_project_token(detail: dict) -> str:
        token = detail.get("projectToken") or detail.get("project_token") or detail.get("token") or ""
        return str(token).strip()

    def _pick_deployment_id(detail: dict) -> str:
        dep_id = detail.get("id") or detail.get("deploymentId") or detail.get("deployment_id") or ""
        return str(dep_id).strip()

    def _as_dict(data: object) -> dict:
        return data if isinstance(data, dict) else {}

    # Always create a new deployment per session using the outgoing prompt.
    new_dep_payload = await noc.create_deployment(auth_token, prompt=create_prompt)
    new_dep = new_dep_payload if isinstance(new_dep_payload, dict) else {}
    if not new_dep:
        new_dep = _as_dict(new_dep_payload.get("data")) if isinstance(new_dep_payload, dict) else {}

    dep_id = _pick_deployment_id(new_dep)
    runtime_host = _pick_runtime_host(new_dep)
    project_token = _pick_project_token(new_dep)

    if runtime_host and project_token:
        if _health_wait_enabled():
            ok = await _wait_runtime_healthy(
                runtime_host,
                project_token=project_token,
                auth_token=auth_token,
                timeout=_health_wait_seconds(),
                interval=_health_poll_seconds(),
            )
            if not ok:
                raise RuntimeError(f"Runtime health check failed before session create: {runtime_host}")
        return {"runtime_host": runtime_host, "project_token": project_token}

    if not dep_id and isinstance(new_dep_payload, dict):
        nested = _as_dict(new_dep_payload.get("data"))
        dep_id = _pick_deployment_id(nested)
        runtime_host = runtime_host or _pick_runtime_host(nested)
        project_token = project_token or _pick_project_token(nested)

    if runtime_host and project_token:
        if _health_wait_enabled():
            ok = await _wait_runtime_healthy(
                runtime_host,
                project_token=project_token,
                auth_token=auth_token,
                timeout=_health_wait_seconds(),
                interval=_health_poll_seconds(),
            )
            if not ok:
                raise RuntimeError(f"Runtime health check failed before session create: {runtime_host}")
        return {"runtime_host": runtime_host, "project_token": project_token}

    if not dep_id:
        raise Exception(f"No deployment ID in response: {new_dep_payload}")

    # Poll until deployment is ready
    for _ in range(24):
        dep_detail_payload = await noc.get_deployment(auth_token, dep_id)
        dep_detail = dep_detail_payload if isinstance(dep_detail_payload, dict) else {}
        runtime_host = _pick_runtime_host(dep_detail)
        project_token = _pick_project_token(dep_detail)

        if runtime_host and project_token:
            if _health_wait_enabled():
                ok = await _wait_runtime_healthy(
                    runtime_host,
                    project_token=project_token,
                    auth_token=auth_token,
                    timeout=_health_wait_seconds(),
                    interval=_health_poll_seconds(),
                )
                if not ok:
                    raise RuntimeError(f"Runtime health check failed before session create: {runtime_host}")
            return {"runtime_host": runtime_host, "project_token": project_token}

        await asyncio.sleep(5.0)

    raise Exception("Deployment did not become ready in time")


async def _auto_register_one_account(task_id: str) -> bool:
    """
    Try auto-registering one account when pool has no available account.
    Returns True when registration succeeds and account is saved to pool.
    """
    base_email = str(os.environ.get("NODEOPS_GMAIL", "feijidfg55@gmail.com")).strip()
    app_password = str(
        os.environ.get("NODEOPS_GMAIL_APP_PASSWORD", "maqk srdy ucjq bsby")
    ).strip()
    proxy_host = str(os.environ.get("NODEOPS_PROXY_HOST", "127.0.0.1")).strip() or "127.0.0.1"
    proxy_type = str(os.environ.get("NODEOPS_PROXY_TYPE", "http")).strip() or "http"
    try:
        proxy_port = int(os.environ.get("NODEOPS_PROXY_PORT", "7897"))
    except Exception:
        proxy_port = 7897

    if not base_email or "@" not in base_email:
        _emit_task_event(task_id, "auto_register_failed", {"error": "NODEOPS_GMAIL is invalid"})
        return False
    if not app_password:
        _emit_task_event(task_id, "auto_register_failed", {"error": "NODEOPS_GMAIL_APP_PASSWORD is empty"})
        return False

    alias = generate_gmail_aliases(base_email, 1)[0]
    _emit_task_event(task_id, "auto_register_started", {
        "email": alias,
        "base_email": base_email,
    })

    try:
        gcfg = GmailConfig(
            email=base_email,
            app_password=app_password,
            proxy_host=proxy_host,
            proxy_port=proxy_port,
            proxy_type=proxy_type,
            delete_best=True,
            poll_interval_s=5.0,
            otp_timeout_s=180,
        )
        rcfg = RegisterConfig(
            redeem_credits=False,
        )
        res = await gmail_auto_register(
            target_email=alias,
            gmail_cfg=gcfg,
            reg_cfg=rcfg,
            save_to_pool=True,
        )
    except Exception as exc:
        logger.error("Task %s: auto register failed: %s", task_id, exc)
        _emit_task_event(task_id, "auto_register_failed", {
            "email": alias,
            "error": str(exc),
        })
        return False

    if not res.ok:
        _emit_task_event(task_id, "auto_register_failed", {
            "email": alias,
            "error": res.error,
        })
        return False

    _emit_task_event(task_id, "auto_register_succeeded", {
        "email": alias,
        "account_id": res.account_id,
    })
    return True


async def _monitor_session(project_name: str, task_id: str, task: dict,
                           account: dict, runtime_host: str,
                           project_token: str, session_id: str,
                           override_idle_timeout: int | None = None) -> str:
    """Monitor a running session with SSE + polling fallback.

    Returns: "completed" | "credit_exhausted" | "stuck_idle" | "error" | "canceled"
    """
    auth_token = account["auth_token"]
    last_rendered_rows: list[dict[str, str]] = []
    poll_interval = 5  # seconds
    idle_timeout_seconds = int(override_idle_timeout or 120)
    kickoff_timeout_seconds = max(
        5, int(os.environ.get("NODEOPS_SESSION_KICKOFF_TIMEOUT_SECONDS", "20"))
    )
    transient_errors = 0
    last_credit_check_at = 0.0
    monitor_started_at = time.monotonic()
    last_activity_at = monitor_started_at
    sse_state: dict[str, Any] = {
        "connected": False,
        "last_activity_at": last_activity_at,
        "credit_exhausted": False,
        "last_error": None,
        "account_exhausted_marked": False,
        "busy_seen": False,
        "last_status": "",
        "last_status_at": 0.0,
    }
    sse_task = asyncio.create_task(
        _consume_sse_stream(
            project_name=project_name,
            task_id=task_id,
            account_id=account.get("id"),
            account_email=account["email"],
            session_index=int(task.get("session_index", 0)),
            runtime_host=runtime_host,
            project_token=project_token,
            session_id=session_id,
            sse_state=sse_state,
        )
    )

    try:
        while True:
            if _stop_events.get(task_id, asyncio.Event()).is_set():
                return "canceled"
            if sse_state.get("credit_exhausted"):
                return "credit_exhausted"

            try:
                # Pull messages as fallback (SSE may disconnect/transiently stall)
                messages_data = await noc.get_messages(
                    runtime_host, project_token, auth_token, session_id
                )
                messages = _normalize_messages(messages_data)
                for msg in messages:
                    role = _normalize_chat_role(_extract_message_role(msg))
                    if role != "user" and _payload_indicates_credit_exhausted(msg):
                        return "credit_exhausted"

                # Cache messages
                _message_cache[task_id] = messages

                rendered_rows = _render_runtime_chat_rows(messages)
                if rendered_rows != last_rendered_rows:
                    _rewrite_session_messages_snapshot(
                        project_name=project_name,
                        task_id=task_id,
                        session_index=int(task.get("session_index", 0)),
                        rows=rendered_rows,
                    )
                    _emit_assistant_row_updates(
                        task_id=task_id,
                        session_id=session_id,
                        session_index=int(task.get("session_index", 0)),
                        previous_rows=last_rendered_rows,
                        current_rows=rendered_rows,
                    )
                    last_rendered_rows = rendered_rows
                    last_activity_at = time.monotonic()
                    transient_errors = 0
                    # New assistant activity: force next-loop credit refresh.
                    last_credit_check_at = 0.0
                else:
                    sse_last = float(sse_state.get("last_activity_at", 0.0) or 0.0)
                    effective_activity = max(last_activity_at, sse_last)
                    if (
                        len(last_rendered_rows) > 1
                        and (time.monotonic() - effective_activity) >= idle_timeout_seconds
                    ):
                        credit_status = await credit_monitor.check_credits(
                            auth_token, account["id"]
                        )
                        _emit_task_event(task_id, "credits_updated", {
                            "credits_remaining": credit_status.get("credits_remaining"),
                            "exhausted": bool(credit_status.get("exhausted", False)),
                            "account_id": account["id"],
                        })
                        if credit_status["exhausted"]:
                            return "credit_exhausted"
                        return "completed"

                # Upstream may accept message but stay idle forever (no busy, no assistant).
                # Switch account early instead of waiting for long idle timeout.
                if (
                    len(last_rendered_rows) <= 1
                    and not sse_state.get("busy_seen")
                    and str(sse_state.get("last_status") or "").lower() == "idle"
                    and (time.monotonic() - monitor_started_at) >= kickoff_timeout_seconds
                ):
                    logger.warning(
                        "Task %s: session %s stuck idle after send for %ss (account=%s)",
                        task_id,
                        session_id,
                        kickoff_timeout_seconds,
                        account.get("email"),
                    )
                    return "stuck_idle"

            except Exception as e:
                error_str = str(e)
                if credit_monitor.is_credit_error(error_str):
                    return "credit_exhausted"
                logger.error(f"Task {task_id} monitor error: {e}")
                transient_errors += 1
                if transient_errors > 10:
                    update_task(project_name, task_id, {
                        "status": "failed",
                        "error": f"Monitor failed: {e}"
                    })
                    return "error"

            # Check credits periodically (about every 30s)
            now = time.monotonic()
            if (now - last_credit_check_at) >= 30:
                last_credit_check_at = now
                try:
                    credit_status = await credit_monitor.check_credits(
                        auth_token, account["id"]
                    )
                    _emit_task_event(task_id, "credits_updated", {
                        "credits_remaining": credit_status.get("credits_remaining"),
                        "exhausted": bool(credit_status.get("exhausted", False)),
                        "account_id": account["id"],
                    })
                    if credit_status["exhausted"]:
                        return "credit_exhausted"
                except Exception:
                    pass

            await asyncio.sleep(poll_interval)
    finally:
        if not sse_task.done():
            sse_task.cancel()
        try:
            await sse_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("SSE consumer finished with error: %s", e)


async def _consume_sse_stream(
    project_name: str,
    task_id: str,
    account_id: str | None,
    account_email: str,
    session_index: int,
    runtime_host: str,
    project_token: str,
    session_id: str,
    sse_state: dict[str, Any],
):
    """Consume runtime SSE and update monitor state."""
    async for event_name, payload in parse_sse_payloads(
        noc.connect_sse(runtime_host, project_token, session_id)
    ):
        if _stop_events.get(task_id, asyncio.Event()).is_set():
            break

        sse_state["connected"] = True
        sse_state["last_activity_at"] = time.monotonic()
        await _flush_sse_event(
            project_name=project_name,
            task_id=task_id,
            account_id=account_id,
            account_email=account_email,
            session_index=session_index,
            session_id=session_id,
            event_name=event_name,
            payload=payload,
            sse_state=sse_state,
        )


async def _flush_sse_event(
    project_name: str,
    task_id: str,
    account_id: str | None,
    account_email: str,
    session_index: int,
    session_id: str,
    event_name: str,
    payload: Any,
    sse_state: dict[str, Any],
):
    # Signal credit exhaustion eagerly if SSE explicitly reports a credit/quota error.
    if _payload_indicates_credit_exhausted(payload):
        sse_state["credit_exhausted"] = True
        if account_id and not sse_state.get("account_exhausted_marked"):
            try:
                account_pool.mark_account_status(account_id, "exhausted")
                sse_state["account_exhausted_marked"] = True
            except Exception as exc:
                logger.warning(
                    "Task %s: failed to mark account exhausted on SSE event: %s",
                    task_id,
                    exc,
                )

    # Track runtime status transitions for kickoff health checks.
    if isinstance(payload, dict):
        payload_type = str(payload.get("type") or "").strip().lower()
        if payload_type == "session.status":
            props = payload.get("properties")
            status_type = ""
            if isinstance(props, dict):
                status_obj = props.get("status")
                if isinstance(status_obj, dict):
                    status_type = str(status_obj.get("type") or "").strip().lower()
                elif status_obj is not None:
                    status_type = str(status_obj).strip().lower()
            if status_type:
                sse_state["last_status"] = status_type
                sse_state["last_status_at"] = time.monotonic()
                if status_type == "busy":
                    sse_state["busy_seen"] = True

def _render_runtime_chat_rows(messages: list[dict]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for msg in messages:
        role = _normalize_chat_role(_extract_message_role(msg))
        content = _extract_message_text(msg).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        row = {"role": role, "content": content}
        prev = out[-1] if out else None
        if prev and prev["role"] == row["role"] and prev["content"] == row["content"]:
            continue
        if prev and prev["role"] == "user" and row["role"] == "assistant" and prev["content"] == row["content"]:
            continue
        out.append(row)
    return out


def _emit_assistant_row_updates(
    task_id: str,
    session_id: str,
    session_index: int,
    previous_rows: list[dict[str, str]],
    current_rows: list[dict[str, str]],
):
    for idx, row in enumerate(current_rows):
        if row.get("role") != "assistant":
            continue
        prev = previous_rows[idx] if idx < len(previous_rows) else None
        if prev and prev.get("role") == "assistant" and prev.get("content") == row.get("content"):
            continue
        payload = {
            "session_id": session_id,
            "session_index": session_index,
            "role": "assistant",
            "content": row.get("content", ""),
        }
        if prev is not None:
            payload["updated"] = True
        _emit_task_event(task_id, "message", payload)


def _rewrite_session_messages_snapshot(
    project_name: str,
    task_id: str,
    session_index: int,
    rows: list[dict[str, str]],
):
    path = session_md_path(project_name, task_id, session_index)
    if not path.exists():
        return

    raw = path.read_text(encoding="utf-8")
    marker = "## Messages"
    if marker in raw:
        idx = raw.find(marker)
        marker_end = raw.find("\n", idx)
        if marker_end == -1:
            header = raw.rstrip("\n") + "\n"
        else:
            header = raw[: marker_end + 1]
        if not header.endswith("\n\n"):
            if header.endswith("\n"):
                header += "\n"
            else:
                header += "\n\n"
    else:
        header = raw.rstrip("\n")
        if header:
            header += "\n\n"
        header += "## Messages\n\n"

    body_lines: list[str] = []
    for row in rows:
        role = str(row.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = str(row.get("content") or "").rstrip()
        if not content:
            continue
        role_tag = "User" if role == "user" else "Assistant"
        body_lines.append(f"[{role_tag}]\n{content}\n\n")

    updated = header + "".join(body_lines)
    if updated != raw:
        path.write_text(updated, encoding="utf-8")


def _emit_task_event(task_id: str, event_type: str, data: dict[str, Any]):
    seq = int(_task_event_seq.get(task_id, 0)) + 1
    _task_event_seq[task_id] = seq
    event = {
        "seq": seq,
        "type": event_type,
        "data": data,
        "at": now_iso(),
    }
    buf = _task_events.setdefault(task_id, [])
    buf.append(event)
    if len(buf) > _EVENT_BUFFER_LIMIT:
        del buf[:-_EVENT_BUFFER_LIMIT]


def _release_task_account_lock(project_name: str, task_id: str):
    """Best-effort lock cleanup for stale/canceled task states."""
    task = get_task(project_name, task_id)
    if not task:
        return
    account_id = str(task.get("current_account_id") or "").strip()
    if not account_id:
        return
    account = account_pool.get_account(account_id)
    if not account:
        return
    if str(account.get("locked_by_task") or "").strip() == task_id:
        try:
            account_pool.release_account(account_id)
        except Exception as exc:
            logger.warning("Failed releasing account lock for task %s: %s", task_id, exc)


def _payload_indicates_credit_exhausted(payload: Any) -> bool:
    """Return True when payload clearly indicates credit/quota exhaustion."""
    if credit_monitor.is_credit_error(str(payload)):
        return True

    if isinstance(payload, dict):
        p_type = str(payload.get("type") or "").strip().lower()
        if p_type == "session.error":
            props = payload.get("properties")
            if isinstance(props, dict):
                err = props.get("error")
                if isinstance(err, dict):
                    err_type = str(err.get("type") or "").strip().lower()
                    err_message = str(err.get("message") or "")
                    err_status = str(err.get("status") or "").strip()
                    if err_type in {"credit", "credits", "quota"}:
                        return True
                    if err_status == "402" and credit_monitor.is_credit_error(err_message):
                        return True
    return False


def _extract_runtime_session_id(session_data: Any) -> str:
    if not isinstance(session_data, dict):
        return ""
    return (
        str(session_data.get("id") or "")
        or str(session_data.get("sessionId") or "")
        or str(session_data.get("session_id") or "")
    ).strip()


def _helper_session_md_path(project_name: str, task_id: str, session_index: int):
    base = session_md_path(project_name, task_id, session_index)
    return base.with_name(f"session-{session_index}-git.md")


def _init_helper_session_file(
    project_name: str,
    task_id: str,
    account_email: str,
    session_index: int,
    nodeops_session_id: str,
):
    path = _helper_session_md_path(project_name, task_id, session_index)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"# Session {session_index} Git - {task_id}\n"
        f"- Account: {account_email}\n"
        f"- NodeOps Session ID: {nodeops_session_id}\n"
        f"- Started: {now_iso()}\n"
        f"- End Reason: (in progress)\n"
        f"\n## Messages\n\n"
    )
    path.write_text(header, encoding="utf-8")
    return path


def _rewrite_helper_session_messages_snapshot(path, rows: list[dict[str, str]]):
    if not path.exists():
        return
    raw = path.read_text(encoding="utf-8")
    marker = "## Messages"
    if marker in raw:
        idx = raw.find(marker)
        marker_end = raw.find("\n", idx)
        if marker_end == -1:
            header = raw.rstrip("\n") + "\n"
        else:
            header = raw[: marker_end + 1]
        if not header.endswith("\n\n"):
            if header.endswith("\n"):
                header += "\n"
            else:
                header += "\n\n"
    else:
        header = raw.rstrip("\n")
        if header:
            header += "\n\n"
        header += "## Messages\n\n"

    body_lines: list[str] = []
    for row in rows:
        role = str(row.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = str(row.get("content") or "").rstrip()
        if not content:
            continue
        role_tag = "User" if role == "user" else "Assistant"
        body_lines.append(f"[{role_tag}]\n{content}\n\n")
    updated = header + "".join(body_lines)
    if updated != raw:
        path.write_text(updated, encoding="utf-8")


def _finalize_helper_session_file(path, end_reason: str):
    if not path.exists():
        return
    raw = path.read_text(encoding="utf-8")
    updated = raw.replace(
        "- End Reason: (in progress)",
        f"- Ended: {now_iso()}\n- End Reason: {end_reason}",
    )
    if updated != raw:
        path.write_text(updated, encoding="utf-8")


async def _monitor_helper_session(
    task_id: str,
    account: dict,
    runtime_host: str,
    project_token: str,
    session_id: str,
    helper_md_path,
    idle_timeout_seconds: int = 300,
    max_seconds: int = 600,
) -> str:
    """
    Side-effect-free helper monitor:
    - does NOT touch main session markdown
    - does NOT update task message cache
    - does NOT emit assistant stream events
    """
    auth_token = account["auth_token"]
    poll_interval = 5
    started_at = time.monotonic()
    last_activity_at = started_at
    last_credit_check_at = 0.0
    transient_errors = 0
    last_rows: list[dict[str, str]] = []

    while (time.monotonic() - started_at) < max_seconds:
        if _stop_events.get(task_id, asyncio.Event()).is_set():
            return "canceled"
        try:
            messages_data = await noc.get_messages(
                runtime_host, project_token, auth_token, session_id
            )
            messages = _normalize_messages(messages_data)

            for msg in messages:
                role = _normalize_chat_role(_extract_message_role(msg))
                if role != "user" and _payload_indicates_credit_exhausted(msg):
                    return "credit_exhausted"

            rows = _render_runtime_chat_rows(messages)
            if rows != last_rows:
                _rewrite_helper_session_messages_snapshot(helper_md_path, rows)
                last_rows = rows
                last_activity_at = time.monotonic()
                transient_errors = 0
            else:
                if len(last_rows) > 1 and (time.monotonic() - last_activity_at) >= idle_timeout_seconds:
                    try:
                        credit_status = await credit_monitor.check_credits(
                            auth_token, account["id"]
                        )
                        if credit_status["exhausted"]:
                            return "credit_exhausted"
                    except Exception:
                        pass
                    return "completed"
        except Exception as exc:
            transient_errors += 1
            if credit_monitor.is_credit_error(str(exc)):
                return "credit_exhausted"
            if transient_errors > 10:
                logger.warning("Task %s: helper monitor failed too many times: %s", task_id, exc)
                return "error"

        now = time.monotonic()
        if (now - last_credit_check_at) >= 30:
            last_credit_check_at = now
            try:
                credit_status = await credit_monitor.check_credits(auth_token, account["id"])
                if credit_status["exhausted"]:
                    return "credit_exhausted"
            except Exception:
                pass

        await asyncio.sleep(poll_interval)

    return "timeout"


def _finalize_credit_exhausted_switch(
    project_name: str,
    task_id: str,
    task: dict,
    account: dict,
    end_reason: str,
    git_commit: str | None,
):
    used_ids = list(task.get("used_account_ids", []))
    if account["id"] not in used_ids:
        used_ids.append(account["id"])
    account_pool.release_account(account["id"], exhausted=True)

    loops = list(task.get("loops", []))
    loops.append({
        "index": int(task.get("loop_count", 0)) + 1,
        "account_email": account["email"],
        "session_id": task.get("current_session_id"),
        "started_at": task.get("updated_at"),
        "ended_at": now_iso(),
        "end_reason": end_reason,
        "git_commit": git_commit,
    })

    update_task(project_name, task_id, {
        "loop_count": int(task.get("loop_count", 0)) + 1,
        "used_account_ids": used_ids,
        "loops": loops,
        "status": "switching",
        "current_account_id": None,
        "current_session_id": None,
        "error": None,
    })


async def _run_git(
    cwd: Path,
    *args: str,
) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return (
        int(proc.returncode or 0),
        stdout.decode(errors="ignore"),
        stderr.decode(errors="ignore"),
    )


def _context_session_paths_for_task(repo_root: Path, task_id: str) -> list[Path]:
    task_dir = repo_root / ".nodeops" / task_id
    if not task_dir.exists():
        return []
    out: list[Path] = []
    for path in sorted(task_dir.glob("session-*.md")):
        if not path.is_file():
            continue
        # Exclude helper session logs: session-<index>-git.md
        if path.name.endswith("-git.md"):
            continue
        out.append(path)
    return out


async def _push_task_context_sessions(
    project_name: str,
    task_id: str,
    loop_index: int,
    end_reason: str,
) -> tuple[bool, str | None, str | None]:
    """
    Push only .nodeops session markdown files for current task before switching account.

    Includes:
      - .nodeops/<task_id>/session-*.md
    Excludes:
      - .nodeops/<task_id>/session-*-git.md
      - any task json / code files
    """
    root = repo_dir(project_name)
    if not (root / ".git").exists():
        return False, None, f"Not a git repository: {root}"

    paths = _context_session_paths_for_task(root, task_id)
    if not paths:
        return True, None, None

    rel_paths = [p.relative_to(root).as_posix() for p in paths]

    rc, _, err = await _run_git(root, "add", "--", *rel_paths)
    if rc != 0:
        return False, None, f"git add failed: {err.strip() or 'unknown error'}"

    rc, staged_out, staged_err = await _run_git(root, "diff", "--cached", "--name-only", "--", *rel_paths)
    if rc != 0:
        return False, None, f"git diff --cached failed: {(staged_err or staged_out).strip() or 'unknown error'}"
    if not staged_out.strip():
        return True, None, None

    commit_msg = (
        f"task {task_id} loop {loop_index} "
        f"{end_reason}: sync nodeops session context"
    )
    rc, commit_out, commit_err = await _run_git(
        root, "commit", "-m", commit_msg, "--", *rel_paths
    )
    commit_text = f"{commit_out}\n{commit_err}".lower()
    if rc != 0:
        if "nothing to commit" in commit_text:
            return True, None, None
        return False, None, f"git commit failed: {(commit_err or commit_out).strip() or 'unknown error'}"

    rc, head_out, head_err = await _run_git(root, "rev-parse", "HEAD")
    if rc != 0:
        return False, None, f"git rev-parse failed: {(head_err or head_out).strip() or 'unknown error'}"
    commit_hash = head_out.strip() or None

    rc, push_out, push_err = await _run_git(root, "push")
    if rc == 0:
        return True, commit_hash, None

    push_text = f"{push_out}\n{push_err}".lower()
    if "non-fast-forward" in push_text or "fetch first" in push_text:
        rc_pull, pull_out, pull_err = await _run_git(root, "pull", "--rebase")
        if rc_pull != 0:
            return False, commit_hash, (
                "git push rejected (non-fast-forward) and git pull --rebase failed: "
                f"{(pull_err or pull_out).strip() or 'unknown error'}"
            )
        rc_retry, retry_out, retry_err = await _run_git(root, "push")
        if rc_retry == 0:
            return True, commit_hash, None
        return False, commit_hash, (
            "git push failed after rebase: "
            f"{(retry_err or retry_out).strip() or 'unknown error'}"
        )

    return False, commit_hash, f"git push failed: {(push_err or push_out).strip() or 'unknown error'}"


async def _get_remote_head(project_name: str) -> str | None:
    """Read remote origin HEAD hash (or None when unavailable)."""
    cwd = str(repo_dir(project_name))
    if not os.path.exists(os.path.join(cwd, ".git")):
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "ls-remote",
            "origin",
            "HEAD",
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return None
        line = stdout.decode(errors="ignore").strip()
        if not line:
            return None
        parts = line.split()
        if not parts:
            return None
        return parts[0].strip() or None
    except Exception as exc:
        logger.warning("Failed to get remote HEAD for %s: %s", project_name, exc)
        return None


async def _agent_push_via_new_session(
    project_name: str,
    task_id: str,
    task: dict,
    account: dict,
    runtime_host: str,
    project_token: str,
    auth_token: str,
    commit_prompt: str,
    timeout_seconds: int = 300,
) -> bool:
    """
    Reuse current deployment, create a short-lived helper session, and ask agent
    to commit+push. Success = remote HEAD changes; fallback = monitor completion
    when HEAD baseline is unavailable.
    """
    if not runtime_host or not project_token or not auth_token:
        logger.warning("Task %s: commit helper missing runtime context", task_id)
        return False

    old_head = await _get_remote_head(project_name)

    try:
        session_data = await noc.create_session(
            runtime_host,
            project_token,
            auth_token,
            title=f"{task_id} commit-push",
            model=task.get("model"),
        )
        session_id = _extract_runtime_session_id(session_data)
        if not session_id:
            logger.error(
                "Task %s: commit session created but id missing: %s",
                task_id,
                session_data,
            )
            return False
    except Exception as exc:
        logger.error("Task %s: create commit session failed: %s", task_id, exc)
        return False

    _emit_task_event(task_id, "commit_session_created", {
        "project": project_name,
        "task_id": task_id,
        "session_id": session_id,
        "purpose": "agent_push",
    })
    helper_session_index = int(task.get("session_index", 0))
    helper_md_path = _init_helper_session_file(
        project_name=project_name,
        task_id=task_id,
        account_email=account["email"],
        session_index=helper_session_index,
        nodeops_session_id=session_id,
    )

    try:
        await noc.send_message(
            runtime_host,
            project_token,
            auth_token,
            session_id,
            commit_prompt,
            model=task.get("model"),
        )
    except Exception as exc:
        logger.error("Task %s: send commit prompt failed: %s", task_id, exc)
        return False

    try:
        end_reason = await _monitor_helper_session(
            task_id=task_id,
            account=account,
            runtime_host=runtime_host,
            project_token=project_token,
            session_id=session_id,
            helper_md_path=helper_md_path,
            idle_timeout_seconds=max(30, int(timeout_seconds)),
            max_seconds=max(120, int(timeout_seconds) * 2),
        )
    except Exception as exc:
        logger.error("Task %s: monitor commit session failed: %s", task_id, exc)
        end_reason = "error"
    finally:
        _finalize_helper_session_file(helper_md_path, end_reason)

    new_head = await _get_remote_head(project_name)
    if old_head and new_head and old_head != new_head:
        logger.info(
            "Task %s: commit helper detected remote HEAD change old=%s new=%s",
            task_id,
            old_head,
            new_head,
        )
        return True

    if old_head is None and end_reason == "completed":
        logger.info(
            "Task %s: commit helper completed; remote HEAD baseline unavailable",
            task_id,
        )
        return True

    logger.warning(
        "Task %s: no remote commit detected after helper session (end_reason=%s old=%s new=%s)",
        task_id,
        end_reason,
        old_head,
        new_head,
    )
    return False


async def _handle_credit_exhausted(project_name: str, task_id: str,
                                   task: dict, account: dict) -> str:
    """Handle credit exhaustion.

    Auto mode: sync → push → switch account → return "continue"
    Oneshot mode: block → return "blocked"
    """
    session_recorder.finalize_session(
        project_name, task_id, account["email"],
        task.get("session_index", 0), "credit_exhausted"
    )

    if task["mode"] == "oneshot":
        account_pool.release_account(account["id"], exhausted=True)
        update_task(project_name, task_id, {
            "status": "blocked",
            "error": "Credit exhausted (oneshot mode)"
        })
        return "blocked"

    commit_prompt = str(task.get("commit_prompt") or "").strip()
    if commit_prompt:
        update_task(project_name, task_id, {"status": "submitting_commit", "error": None})
        runtime_host = str(
            task.get("current_runtime_host")
            or account.get("runtime_host")
            or ""
        ).strip()
        project_token = str(
            task.get("current_project_token")
            or account.get("project_token")
            or ""
        ).strip()
        push_success = await _agent_push_via_new_session(
            project_name=project_name,
            task_id=task_id,
            task=task,
            account=account,
            runtime_host=runtime_host,
            project_token=project_token,
            auth_token=account["auth_token"],
            commit_prompt=commit_prompt,
            timeout_seconds=300,
        )
        if push_success:
            context_ok, context_commit, context_err = await _push_task_context_sessions(
                project_name=project_name,
                task_id=task_id,
                loop_index=int(task.get("loop_count", 0)) + 1,
                end_reason="credit_exhausted_agent_pushed",
            )
            if not context_ok:
                account_pool.release_account(account["id"], exhausted=True)
                update_task(project_name, task_id, {
                    "status": "blocked",
                    "error": f"Context push failed before switch: {context_err}",
                    "current_account_id": None,
                    "current_session_id": None,
                })
                _emit_task_event(task_id, "context_push_failed", {
                    "project": project_name,
                    "task_id": task_id,
                    "reason": "credit_exhausted_agent_pushed",
                    "error": context_err,
                })
                return "blocked"
            _finalize_credit_exhausted_switch(
                project_name=project_name,
                task_id=task_id,
                task=task,
                account=account,
                end_reason="credit_exhausted_agent_pushed",
                git_commit=context_commit,
            )
            logger.info(
                "Task %s: helper commit session succeeded, switching account (loop %s)",
                task_id,
                int(task.get("loop_count", 0)) + 1,
            )
            return "continue"

        if not bool(task.get("fallback_sync", True)):
            account_pool.release_account(account["id"], exhausted=True)
            update_task(project_name, task_id, {
                "status": "blocked",
                "error": "Agent push failed, fallback_sync disabled, waiting for manual intervention",
                "current_account_id": None,
                "current_session_id": None,
            })
            return "blocked"

        logger.info("Task %s: helper commit session failed, fallback to local sync", task_id)

    # Fallback path: sync workspace locally and push from local git.
    commit_hash = await _sync_and_push(project_name, task_id, task, account, "credit_exhausted")
    context_ok, context_commit, context_err = await _push_task_context_sessions(
        project_name=project_name,
        task_id=task_id,
        loop_index=int(task.get("loop_count", 0)) + 1,
        end_reason="credit_exhausted",
    )
    if not context_ok:
        account_pool.release_account(account["id"], exhausted=True)
        update_task(project_name, task_id, {
            "status": "blocked",
            "error": f"Context push failed before switch: {context_err}",
            "current_account_id": None,
            "current_session_id": None,
        })
        _emit_task_event(task_id, "context_push_failed", {
            "project": project_name,
            "task_id": task_id,
            "reason": "credit_exhausted",
            "error": context_err,
        })
        return "blocked"
    _finalize_credit_exhausted_switch(
        project_name=project_name,
        task_id=task_id,
        task=task,
        account=account,
        end_reason="credit_exhausted",
        git_commit=context_commit or commit_hash,
    )
    logger.info(
        "Task %s: switching to next account after credit_exhausted fallback (loop %s)",
        task_id,
        int(task.get("loop_count", 0)) + 1,
    )
    return "continue"


async def _handle_stuck_idle(project_name: str, task_id: str,
                             task: dict, account: dict) -> str:
    """Handle session that remains idle right after send (no busy / no output)."""
    session_recorder.finalize_session(
        project_name, task_id, account["email"],
        task.get("session_index", 0), "stuck_idle"
    )

    if task["mode"] == "oneshot":
        account_pool.release_account(account["id"], exhausted=True)
        update_task(project_name, task_id, {
            "status": "blocked",
            "error": "Session stayed idle after send (oneshot mode)"
        })
        return "blocked"

    context_ok, context_commit, context_err = await _push_task_context_sessions(
        project_name=project_name,
        task_id=task_id,
        loop_index=int(task.get("loop_count", 0)) + 1,
        end_reason="stuck_idle",
    )
    if not context_ok:
        account_pool.release_account(account["id"], exhausted=True)
        update_task(project_name, task_id, {
            "status": "blocked",
            "error": f"Context push failed before switch: {context_err}",
            "current_account_id": None,
            "current_session_id": None,
        })
        _emit_task_event(task_id, "context_push_failed", {
            "project": project_name,
            "task_id": task_id,
            "reason": "stuck_idle",
            "error": context_err,
        })
        return "blocked"

    used_ids = task.get("used_account_ids", [])
    if account["id"] not in used_ids:
        used_ids.append(account["id"])
    account_pool.release_account(account["id"], exhausted=True)

    loops = task.get("loops", [])
    loops.append({
        "index": task["loop_count"] + 1,
        "account_email": account["email"],
        "session_id": task.get("current_session_id"),
        "started_at": task.get("updated_at"),
        "ended_at": now_iso(),
        "end_reason": "stuck_idle",
        "git_commit": context_commit,
    })

    update_task(project_name, task_id, {
        "loop_count": task["loop_count"] + 1,
        "used_account_ids": used_ids,
        "loops": loops,
        "status": "switching",
        "current_account_id": None,
        "current_session_id": None,
        "error": None,
    })
    _emit_task_event(task_id, "session_stuck_idle", {
        "project": project_name,
        "task_id": task_id,
        "account_id": account.get("id"),
        "account_email": account.get("email"),
        "session_id": task.get("current_session_id"),
    })

    logger.warning(
        "Task %s: switching account due to stuck idle session (account=%s)",
        task_id,
        account.get("email"),
    )
    return "continue"


async def _sync_and_push(project_name: str, task_id: str,
                         task: dict, account: dict, reason: str):
    """Download workspace and git push."""
    runtime_host = task.get("current_runtime_host", account.get("runtime_host"))
    project_token = task.get("current_project_token", account.get("project_token"))
    auth_token = account["auth_token"]

    if not runtime_host or not project_token:
        logger.warning(f"Task {task_id}: no runtime info, skip workspace sync")
        return None

    update_task(project_name, task_id, {"status": "syncing"})

    try:
        await workspace_sync.sync_workspace_to_repo(
            runtime_host, project_token, auth_token, project_name
        )
    except Exception as e:
        logger.error(f"Task {task_id}: workspace sync failed: {e}")

    update_task(project_name, task_id, {"status": "pushing"})

    try:
        commit = await workspace_sync.git_push(
            project_name,
            f"Loop {task['loop_count'] + 1} - {reason}"
        )
        if commit:
            logger.info(f"Task {task_id}: pushed commit {commit}")
        return commit
    except Exception as e:
        logger.error(f"Task {task_id}: git push failed: {e}")
        return None
