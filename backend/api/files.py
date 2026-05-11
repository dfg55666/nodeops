"""Workspace file proxy routes."""
import base64
from pathlib import Path, PurePosixPath
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
async def get_file_tree_for_task(
    project_name: str,
    task_id: str,
    path: str = "",
    account_id: str = "",
):
    """Get file tree using the task's current account/deployment."""
    task, acc, runtime_host, project_token = _resolve_task_runtime(
        project_name,
        task_id,
        account_id=account_id,
    )

    data = await noc.get_file_tree(runtime_host, project_token, acc["auth_token"], path)
    return {"success": True, "data": data}


@router.get("/content/task")
async def get_file_content_for_task(
    project_name: str,
    task_id: str,
    path: str = Query(...),
    account_id: str = "",
):
    """Get file content using the task's current account/deployment."""
    task, acc, runtime_host, project_token = _resolve_task_runtime(
        project_name,
        task_id,
        account_id=account_id,
    )
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


@router.get("/download")
async def download_path(
    account_id: str,
    path: str = Query(...),
    is_dir: bool = Query(False),
):
    """
    Save workspace path to local `download/` directory.
    - file: save one file
    - directory: recursively save all files
    """
    acc = account_pool.get_account(account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    if not acc.get("runtime_host") or not acc.get("project_token"):
        raise HTTPException(400, "Account has no active deployment")

    return await _download_workspace_path_to_local(
        runtime_host=acc["runtime_host"],
        project_token=acc["project_token"],
        auth_token=acc["auth_token"],
        path=path,
        is_dir=is_dir,
    )


@router.get("/download/task")
async def download_task_path(
    project_name: str,
    task_id: str,
    path: str = Query(...),
    is_dir: bool = Query(False),
    account_id: str = "",
):
    """Save workspace path to local `download/` using task runtime context."""
    task, acc, runtime_host, project_token = _resolve_task_runtime(
        project_name,
        task_id,
        account_id=account_id,
    )
    return await _download_workspace_path_to_local(
        runtime_host=runtime_host,
        project_token=project_token,
        auth_token=acc["auth_token"],
        path=path,
        is_dir=is_dir,
    )


def _resolve_task_runtime(project_name: str, task_id: str, account_id: str = ""):
    from backend.services.task_engine import get_task

    task = get_task(project_name, task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    resolved_account_id = str(task.get("current_account_id") or "").strip()
    if not resolved_account_id:
        resolved_account_id = str(account_id or "").strip()
    if not resolved_account_id:
        raise HTTPException(400, "Task has no account context (account_id required)")

    acc = account_pool.get_account(resolved_account_id)
    if not acc:
        raise HTTPException(404, "Task account not found in pool")

    runtime_host = str(task.get("current_runtime_host") or acc.get("runtime_host") or "").strip()
    project_token = str(task.get("current_project_token") or acc.get("project_token") or "").strip()
    if not runtime_host or not project_token:
        raise HTTPException(400, "Task has no active deployment runtime info")
    return task, acc, runtime_host, project_token


async def _download_workspace_path_to_local(
    runtime_host: str,
    project_token: str,
    auth_token: str,
    path: str,
    is_dir: bool,
):
    clean_path = _normalize_workspace_path(path)
    if not clean_path:
        raise HTTPException(400, "Path is required")

    download_root = _download_root()
    download_root.mkdir(parents=True, exist_ok=True)
    saved_paths: list[str] = []

    if is_dir:
        file_paths = await _collect_workspace_files(
            runtime_host,
            project_token,
            auth_token,
            clean_path,
        )
        target_dir = _safe_join_download_root(download_root, clean_path)
        target_dir.mkdir(parents=True, exist_ok=True)
        for remote_file_path in file_paths:
            content_bytes = await noc.get_file_content(
                runtime_host,
                project_token,
                auth_token,
                remote_file_path,
            )
            local_file_path = _safe_join_download_root(download_root, remote_file_path)
            local_file_path.parent.mkdir(parents=True, exist_ok=True)
            local_file_path.write_bytes(content_bytes)
            saved_paths.append(str(local_file_path))
        return {
            "success": True,
            "data": {
                "saved_to": str(target_dir),
                "saved_count": len(saved_paths),
                "is_dir": True,
                "source_path": clean_path,
            },
        }

    content_bytes = await noc.get_file_content(runtime_host, project_token, auth_token, clean_path)
    local_file_path = _safe_join_download_root(download_root, clean_path)
    local_file_path.parent.mkdir(parents=True, exist_ok=True)
    local_file_path.write_bytes(content_bytes)
    return {
        "success": True,
        "data": {
            "saved_to": str(local_file_path),
            "saved_count": 1,
            "is_dir": False,
            "source_path": clean_path,
        },
    }


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


def _normalize_workspace_path(path: str) -> str:
    p = str(path or "").strip().replace("\\", "/").lstrip("/")
    while "//" in p:
        p = p.replace("//", "/")
    return p


def _extract_tree_entries(tree: object) -> list[dict]:
    if isinstance(tree, list):
        return [entry for entry in tree if isinstance(entry, dict)]
    if isinstance(tree, dict):
        raw = tree.get("files") or tree.get("entries") or tree.get("children") or []
        if isinstance(raw, list):
            return [entry for entry in raw if isinstance(entry, dict)]
    return []


def _entry_path(entry: dict, parent_path: str) -> str:
    raw_path = _normalize_workspace_path(str(entry.get("path") or ""))
    if raw_path:
        return raw_path
    name = _normalize_workspace_path(str(entry.get("name") or ""))
    if not name:
        return ""
    if not parent_path:
        return name
    return _normalize_workspace_path(f"{parent_path}/{name}")


def _is_dir_entry(entry: dict) -> bool:
    entry_type = str(entry.get("type", "")).strip().lower()
    if entry_type in {"directory", "dir", "folder", "tree"}:
        return True
    if entry.get("is_dir") is True:
        return True
    if isinstance(entry.get("children"), list):
        return True
    return False


async def _collect_workspace_files(
    runtime_host: str,
    project_token: str,
    auth_token: str,
    base_path: str,
) -> list[str]:
    tree = await noc.get_file_tree(runtime_host, project_token, auth_token, base_path)
    entries = _extract_tree_entries(tree)
    file_paths: list[str] = []

    for entry in entries:
        if entry.get("ignored"):
            continue
        entry_path = _entry_path(entry, base_path)
        if not entry_path:
            continue
        if _is_dir_entry(entry):
            file_paths.extend(
                await _collect_workspace_files(
                    runtime_host,
                    project_token,
                    auth_token,
                    entry_path,
                )
            )
        else:
            file_paths.append(entry_path)

    return file_paths


def _download_root() -> Path:
    return Path(__file__).resolve().parents[2] / "download"


def _safe_join_download_root(root: Path, workspace_path: str) -> Path:
    rel = PurePosixPath(_normalize_workspace_path(workspace_path))
    if not rel.parts:
        raise HTTPException(400, "Invalid empty path")
    if any(part in {"", ".", ".."} for part in rel.parts):
        raise HTTPException(400, "Invalid path")
    safe_relative = Path(*rel.parts)
    target = (root / safe_relative).resolve()
    root_resolved = root.resolve()
    if root_resolved not in target.parents and target != root_resolved:
        raise HTTPException(400, "Invalid path")
    return target
