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
from typing import Any
from backend.storage.file_store import (
    task_json, tasks_dir, project_json, read_json, write_json, now_iso, repo_dir,
)
from backend.services import nodeops_client as noc
from backend.services import account_pool
from backend.services import workspace_sync
from backend.services import session_recorder
from backend.services import credit_monitor
from backend.services.register import (
    GmailConfig,
    RegisterConfig,
    generate_gmail_aliases,
    gmail_auto_register,
)

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
    """Get cached messages for an active task."""
    return _message_cache.get(task_id, [])


def is_task_running(task_id: str) -> bool:
    return task_id in _active_tasks and not _active_tasks[task_id].done()


async def create_empty_session(project_name: str, task_id: str) -> dict:
    """Create an empty upstream session for a task without starting task loop."""
    task = get_task(project_name, task_id)
    if not task:
        raise ValueError(f"Task {task_id} not found")

    active_statuses = {
        "running", "monitoring", "pending", "switching",
        "syncing", "pushing", "acquiring_account", "auto_registering_account",
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

    deployment_info = await _ensure_deployment(account)
    runtime_host = deployment_info["runtime_host"]
    project_token = deployment_info["project_token"]

    next_session_index = int(task.get("session_index", 0)) + 1
    session_data = await noc.create_session(
        runtime_host, project_token, account["auth_token"],
        title=f"{task_id} manual-{next_session_index}",
    )
    session_id = (
        str(session_data.get("id") or "")
        or str(session_data.get("sessionId") or "")
        or str(session_data.get("session_id") or "")
    ).strip()
    if not session_id:
        raise ValueError(f"session created but id missing: {session_data}")

    used_ids = list(task.get("used_account_ids", []))
    if account["id"] not in used_ids:
        used_ids.append(account["id"])

    update_task(project_name, task_id, {
        "current_account_id": account["id"],
        "current_runtime_host": runtime_host,
        "current_project_token": project_token,
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
        "Task %s created manual empty session %s using account %s",
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
        "account_dir": account["email"].replace("@", "_at_").replace("+", "_plus_"),
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
            })

            # ── Step 2: Ensure deployment ──
            try:
                deployment_info = await _ensure_deployment(account)
                runtime_host = deployment_info["runtime_host"]
                project_token = deployment_info["project_token"]
                update_task(project_name, task_id, {
                    "current_runtime_host": runtime_host,
                    "current_project_token": project_token,
                })
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

            elif end_reason == "error":
                account_pool.release_account(account["id"])
                break

            elif end_reason == "canceled":
                account_pool.release_account(account["id"])
                break

    except asyncio.CancelledError:
        logger.info(f"Task {task_id} was canceled")
        update_task(project_name, task_id, {"status": "canceled"})
    except Exception as e:
        logger.error(f"Task {task_id} unexpected error: {e}", exc_info=True)
        update_task(project_name, task_id, {
            "status": "failed",
            "error": str(e),
        })
    finally:
        _active_tasks.pop(task_id, None)
        _stop_events.pop(task_id, None)


# ─── Helpers ─────────────────────────────────────────────────────────

async def _ensure_deployment(account: dict) -> dict:
    """Make sure an account has an active deployment. Returns {runtime_host, project_token}."""
    auth_token = account["auth_token"]

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

    # If account already has deployment info, verify it with an authenticated
    # runtime call. `/health` may return 401 on some runtime clusters even when
    # runtime is usable.
    if account.get("runtime_host") and account.get("project_token"):
        try:
            await noc.list_sessions(
                account["runtime_host"],
                account["project_token"],
                auth_token,
            )
            return {
                "runtime_host": account["runtime_host"],
                "project_token": account["project_token"],
            }
        except Exception as e:
            logger.info(
                "Existing deployment validation failed for %s, creating new: %s",
                account["email"],
                e,
            )

    # List existing deployments
    deployments_payload = await noc.list_deployments(auth_token)
    deploy_list: list[dict] = []
    if isinstance(deployments_payload, list):
        deploy_list = [x for x in deployments_payload if isinstance(x, dict)]
    elif isinstance(deployments_payload, dict):
        payload_data = _as_dict(deployments_payload.get("data")) if "data" in deployments_payload else deployments_payload
        raw_list = payload_data.get("deployments") or payload_data.get("items") or payload_data.get("list") or []
        if isinstance(raw_list, list):
            deploy_list = [x for x in raw_list if isinstance(x, dict)]

    if deploy_list:
        dep = deploy_list[0]
        dep_id = _pick_deployment_id(dep)
        runtime_host = _pick_runtime_host(dep)
        project_token = _pick_project_token(dep)

        # If list item misses runtime/token, fetch detail.
        if dep_id and (not runtime_host or not project_token):
            dep_detail_payload = await noc.get_deployment(auth_token, dep_id)
            dep_detail = dep_detail_payload if isinstance(dep_detail_payload, dict) else {}
            runtime_host = runtime_host or _pick_runtime_host(dep_detail)
            project_token = project_token or _pick_project_token(dep_detail)

        if runtime_host and project_token:
            account_pool.update_account(account["id"], {
                "deployment_id": dep_id,
                "runtime_host": runtime_host,
                "project_token": project_token,
            })
            return {"runtime_host": runtime_host, "project_token": project_token}

    # Create new deployment
    new_dep_payload = await noc.create_deployment(auth_token)
    new_dep = new_dep_payload if isinstance(new_dep_payload, dict) else {}
    dep_id = _pick_deployment_id(new_dep)
    if not dep_id and isinstance(new_dep_payload, dict):
        nested = _as_dict(new_dep_payload.get("data"))
        dep_id = _pick_deployment_id(nested)
    if not dep_id:
        raise Exception(f"No deployment ID in response: {new_dep_payload}")

    # Poll until deployment is ready
    for _ in range(24):
        dep_detail_payload = await noc.get_deployment(auth_token, dep_id)
        dep_detail = dep_detail_payload if isinstance(dep_detail_payload, dict) else {}
        runtime_host = _pick_runtime_host(dep_detail)
        project_token = _pick_project_token(dep_detail)

        if runtime_host and project_token:
            account_pool.update_account(account["id"], {
                "deployment_id": dep_id,
                "runtime_host": runtime_host,
                "project_token": project_token,
            })
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
            create_runtime=True,
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
                           project_token: str, session_id: str) -> str:
    """Monitor a running session with SSE + polling fallback.

    Returns: "completed" | "credit_exhausted" | "error" | "canceled"
    """
    auth_token = account["auth_token"]
    last_message_count = 0
    poll_interval = 5  # seconds
    idle_timeout_seconds = 120
    transient_errors = 0
    last_credit_check_at = 0.0
    last_activity_at = time.monotonic()
    sse_state: dict[str, Any] = {
        "connected": False,
        "last_activity_at": last_activity_at,
        "credit_exhausted": False,
        "last_error": None,
        "account_exhausted_marked": False,
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

                # Cache messages
                _message_cache[task_id] = messages

                # Record new messages
                if len(messages) > last_message_count:
                    for msg in messages[last_message_count:]:
                        role = _extract_message_role(msg)
                        content = _extract_message_text(msg)
                        if str(role).lower() != "user" and _payload_indicates_credit_exhausted(msg):
                            return "credit_exhausted"
                        session_recorder.append_message(
                            project_name, task_id, account["email"],
                            task["session_index"], role, content
                        )
                        _emit_task_event(task_id, "message", {
                            "session_id": session_id,
                            "session_index": task.get("session_index", 0),
                            "role": role,
                            "content": content,
                            "raw": msg,
                        })
                    last_message_count = len(messages)
                    last_activity_at = time.monotonic()
                    transient_errors = 0
                else:
                    sse_last = float(sse_state.get("last_activity_at", 0.0) or 0.0)
                    effective_activity = max(last_activity_at, sse_last)
                    if (
                        last_message_count > 1
                        and (time.monotonic() - effective_activity) >= idle_timeout_seconds
                    ):
                        credit_status = await credit_monitor.check_credits(
                            auth_token, account["id"]
                        )
                        if credit_status["exhausted"]:
                            return "credit_exhausted"
                        return "completed"

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
    """Consume runtime SSE, append raw stream to session record, and emit task events."""
    event_name = "message"
    data_lines: list[str] = []

    async for line in noc.connect_sse(runtime_host, project_token, session_id):
        if _stop_events.get(task_id, asyncio.Event()).is_set():
            break

        sse_state["connected"] = True
        sse_state["last_activity_at"] = time.monotonic()

        if line is None:
            continue
        line = str(line)

        if line.startswith(":"):
            # SSE comment / heartbeat line
            session_recorder.append_raw_sse(
                project_name, task_id, account_email, session_index, line
            )
            continue

        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip() or "message"
            continue

        if line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())
            continue

        if line.strip() == "":
            if data_lines:
                await _flush_sse_event(
                    project_name=project_name,
                    task_id=task_id,
                    account_id=account_id,
                    account_email=account_email,
                    session_index=session_index,
                    session_id=session_id,
                    event_name=event_name,
                    data_text="\n".join(data_lines),
                    sse_state=sse_state,
                )
                data_lines.clear()
                event_name = "message"
            continue

        # Unknown line type: preserve as data to avoid loss.
        data_lines.append(line)

    # Flush trailing event, if any.
    if data_lines:
        await _flush_sse_event(
            project_name=project_name,
            task_id=task_id,
            account_id=account_id,
            account_email=account_email,
            session_index=session_index,
            session_id=session_id,
            event_name=event_name,
            data_text="\n".join(data_lines),
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
    data_text: str,
    sse_state: dict[str, Any],
):
    raw_chunk = f"event: {event_name}\ndata: {data_text}\n"
    session_recorder.append_raw_sse(
        project_name, task_id, account_email, session_index, raw_chunk
    )

    payload: Any = data_text
    try:
        payload = json.loads(data_text)
    except Exception:
        pass

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

    _emit_task_event(task_id, "runtime_sse", {
        "session_id": session_id,
        "session_index": session_index,
        "event": event_name,
        "data": payload,
    })


def _normalize_messages(messages_data: Any) -> list[dict]:
    if isinstance(messages_data, list):
        return [m for m in messages_data if isinstance(m, dict)]
    if isinstance(messages_data, dict):
        messages = (
            messages_data.get("messages")
            or messages_data.get("items")
            or messages_data.get("data")
            or []
        )
        if isinstance(messages, list):
            return [m for m in messages if isinstance(m, dict)]
    return []


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

    # Auto mode: sync and continue
    commit_hash = await _sync_and_push(project_name, task_id, task, account, "credit_exhausted")

    # Release and mark account exhausted
    used_ids = task.get("used_account_ids", [])
    if account["id"] not in used_ids:
        used_ids.append(account["id"])
    account_pool.release_account(account["id"], exhausted=True)

    # Record loop
    loops = task.get("loops", [])
    loops.append({
        "index": task["loop_count"] + 1,
        "account_email": account["email"],
        "session_id": task.get("current_session_id"),
        "started_at": task.get("updated_at"),
        "ended_at": now_iso(),
        "end_reason": "credit_exhausted",
        "git_commit": commit_hash,
    })

    update_task(project_name, task_id, {
        "loop_count": task["loop_count"] + 1,
        "used_account_ids": used_ids,
        "loops": loops,
        "status": "switching",
        "current_account_id": None,
        "current_session_id": None,
    })

    logger.info(f"Task {task_id}: switching to next account (loop {task['loop_count'] + 1})")
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


def _extract_message_text(msg: dict) -> str:
    """Extract readable text from a message object."""
    # Messages may have `content` as string or `parts` as list.
    if isinstance(msg.get("content"), str):
        return msg["content"]

    parts = msg.get("parts", msg.get("content", []))
    if isinstance(parts, list):
        texts = []
        for part in parts:
            if isinstance(part, dict) and part.get("type") == "text":
                texts.append(part.get("text", ""))
            elif isinstance(part, str):
                texts.append(part)
        joined = "\n".join([t for t in texts if str(t).strip()])
        if joined.strip():
            return joined

    # NodeOps often puts structured errors under msg.info.error
    info = msg.get("info")
    if isinstance(info, dict):
        err = info.get("error")
        if isinstance(err, dict):
            err_name = str(err.get("name") or "").strip()
            err_data = err.get("data")
            if isinstance(err_data, dict):
                msg_text = str(err_data.get("message") or "").strip()
                status_code = err_data.get("statusCode")
                if msg_text:
                    if status_code is not None and str(status_code).strip():
                        return f"[error:{status_code}] {msg_text}"
                    if err_name:
                        return f"[{err_name}] {msg_text}"
                    return msg_text
            if err_name:
                return f"[{err_name}]"

    return str(msg.get("content", msg.get("text", "")))


def _extract_message_role(msg: dict) -> str:
    """Extract normalized role from runtime message payload."""
    role = msg.get("role")
    if role:
        return str(role).strip().lower()
    info = msg.get("info")
    if isinstance(info, dict):
        info_role = info.get("role")
        if info_role:
            return str(info_role).strip().lower()
    return "unknown"
