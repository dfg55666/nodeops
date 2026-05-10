"""Workspace file proxy routes."""
import base64
from fastapi import APIRouter, HTTPException, Query
from backend.services import nodeops_client as noc
from backend.services import account_pool
from backend.services import workspace_sync
from backend.storage.file_store import repo_dir

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/tree")
async def get_file_tree(account_id: str, path: str = ""):
    """Get workspace directory listing."""
    acc = account_pool.get_account(account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    if not acc.get("runtime_host"):
        raise HTTPException(400, "Account has no active deployment")

    data = await noc.get_file_tree(
        acc["runtime_host"], acc["project_token"], acc["auth_token"], path
    )
    return {"success": True, "data": data}


@router.get("/content")
async def get_file_content(account_id: str, path: str = Query(...)):
    """Get file content from workspace."""
    acc = account_pool.get_account(account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    if not acc.get("runtime_host") or not acc.get("project_token"):
        raise HTTPException(400, "Account has no active deployment")

    content_bytes = await noc.get_file_content(
        acc["runtime_host"], acc["project_token"], acc["auth_token"], path
    )

    return _serialize_content(content_bytes)


@router.get("/status")
async def get_file_status(account_id: str):
    """Get workspace file status."""
    acc = account_pool.get_account(account_id)
    if not acc:
        raise HTTPException(404, "Account not found")

    data = await noc.get_file_status(
        acc["runtime_host"], acc["project_token"], acc["auth_token"]
    )
    return {"success": True, "data": data}


@router.get("/tree/task")
async def get_file_tree_for_task(project_name: str, task_id: str, path: str = ""):
    """Get file tree using the task's current account/deployment."""
    task, acc, runtime_host, project_token = _resolve_task_runtime(project_name, task_id)

    data = await noc.get_file_tree(runtime_host, project_token, acc["auth_token"], path)
    return {"success": True, "data": data}


@router.get("/content/task")
async def get_file_content_for_task(project_name: str, task_id: str, path: str = Query(...)):
    """Get file content using the task's current account/deployment."""
    task, acc, runtime_host, project_token = _resolve_task_runtime(project_name, task_id)
    content_bytes = await noc.get_file_content(
        runtime_host, project_token, acc["auth_token"], path
    )
    return _serialize_content(content_bytes)


@router.post("/download-workspace")
async def download_workspace(account_id: str, project_name: str):
    """
    Pull the remote workspace into local project repo.
    This powers manual sync in oneshot mode.
    """
    acc = account_pool.get_account(account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    if not acc.get("runtime_host") or not acc.get("project_token"):
        raise HTTPException(400, "Account has no active deployment")

    target_repo = repo_dir(project_name)
    if not target_repo.exists():
        raise HTTPException(404, "Project repo not found")

    ok = await workspace_sync.sync_workspace_to_repo(
        acc["runtime_host"],
        acc["project_token"],
        acc["auth_token"],
        project_name,
    )
    return {"success": True, "data": {"synced": bool(ok)}}


@router.post("/download-workspace/task")
async def download_workspace_for_task(project_name: str, task_id: str):
    """Pull remote workspace into local repo by resolving task runtime context."""
    task, acc, runtime_host, project_token = _resolve_task_runtime(project_name, task_id)
    ok = await workspace_sync.sync_workspace_to_repo(
        runtime_host,
        project_token,
        acc["auth_token"],
        project_name,
    )
    return {"success": True, "data": {"synced": bool(ok)}}


def _resolve_task_runtime(project_name: str, task_id: str):
    from backend.services.task_engine import get_task

    task = get_task(project_name, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if not task.get("current_account_id"):
        raise HTTPException(400, "Task has no active account")

    acc = account_pool.get_account(task["current_account_id"])
    if not acc:
        raise HTTPException(404, "Task account not found")

    runtime_host = str(task.get("current_runtime_host") or acc.get("runtime_host") or "").strip()
    project_token = str(task.get("current_project_token") or acc.get("project_token") or "").strip()
    if not runtime_host or not project_token:
        raise HTTPException(400, "Task has no active deployment runtime info")
    return task, acc, runtime_host, project_token


def _serialize_content(content_bytes: bytes):
    try:
        text = content_bytes.decode("utf-8")
        return {"success": True, "data": text, "is_binary": False}
    except UnicodeDecodeError:
        content_b64 = base64.b64encode(content_bytes).decode("ascii")
        return {
            "success": True,
            "data": content_b64,
            "is_binary": True,
            "encoding": "base64",
        }
