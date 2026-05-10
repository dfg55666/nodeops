"""Skill API — simplified endpoints for Claude Code / external AI tools.

These are thin wrappers that expose the most common operations
with minimal request/response complexity.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from backend.services import task_engine
from backend.services import account_pool
from backend.services import nodeops_client as noc
from backend.storage.file_store import DATA_DIR, read_json

router = APIRouter(prefix="/api/skills", tags=["skills"])


class TaskCreateRequest(BaseModel):
    project: str | None = None
    mode: str = "auto"
    message: str | None = None
    prompt: str | None = None
    max_loops: int = 10


@router.post("/task/create")
async def skill_create_task(req: TaskCreateRequest):
    """Create and immediately start a task."""
    try:
        message = (req.prompt or req.message or "").strip()
        if not message:
            raise ValueError("prompt or message is required")

        project_name = (req.project or "").strip()
        if not project_name:
            projects_path = DATA_DIR / "projects"
            if projects_path.exists():
                candidates = sorted([p.name for p in projects_path.iterdir() if p.is_dir()])
                if candidates:
                    project_name = candidates[0]
        if not project_name:
            raise ValueError("project is required (or create at least one project first)")

        task = task_engine.create_task(
            project_name=project_name,
            mode=req.mode,
            message=message,
            max_loops=req.max_loops,
        )
        await task_engine.start_task(project_name, task["id"])
        return {
            "task_id": task["id"],
            "project": project_name,
            "status": "running",
        }
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/task/status")
def skill_task_status(project: str | None = Query(None), task_id: str = Query(...)):
    """Get task status (simplified)."""
    task = None
    if project:
        task = task_engine.get_task(project, task_id)
    else:
        for candidate in task_engine.list_all_tasks():
            if str(candidate.get("id")) == task_id:
                task = candidate
                break
    if not task:
        raise HTTPException(404, "Task not found")
    return {
        "task_id": task["id"],
        "project": task["project"],
        "status": task["status"],
        "mode": task["mode"],
        "loop_count": task.get("loop_count", 0),
        "max_loops": task.get("max_loops", 10),
        "current_account": task.get("current_account_id"),
        "current_session_id": task.get("current_session_id"),
        "current_runtime_host": task.get("current_runtime_host"),
        "error": task.get("error"),
    }


@router.get("/task/list")
def skill_list_tasks(project: str | None = None):
    """List all tasks or tasks for a specific project."""
    if project:
        tasks = task_engine.list_tasks(project)
    else:
        tasks = task_engine.list_all_tasks()
    return [
        {
            "task_id": t["id"],
            "project": t["project"],
            "status": t["status"],
            "mode": t["mode"],
            "loop_count": t.get("loop_count", 0),
        }
        for t in tasks
    ]


@router.post("/task/cancel")
async def skill_cancel_task(project: str | None = Query(None), task_id: str = Query(...)):
    """Cancel a running task."""
    if not project:
        for candidate in task_engine.list_all_tasks():
            if str(candidate.get("id")) == task_id:
                project = str(candidate.get("project", ""))
                break
    if not project:
        raise HTTPException(404, "Task not found")
    await task_engine.cancel_task(project, task_id)
    return {"task_id": task_id, "status": "canceled"}


@router.get("/project/list")
def skill_list_projects():
    """List all projects."""
    projects_path = DATA_DIR / "projects"
    if not projects_path.exists():
        return []
    result = []
    for pdir in sorted(projects_path.iterdir()):
        if pdir.is_dir():
            pj = read_json(pdir / "project.json")
            if pj:
                tasks_path = pdir / "tasks"
                task_count = len(list(tasks_path.glob("*.json"))) if tasks_path.exists() else 0
                result.append({
                    "name": pj.get("name"),
                    "github_url": pj.get("github_url"),
                    "task_count": task_count,
                })
    return result


@router.get("/file/tree")
async def skill_file_tree(project: str | None = Query(None),
                          task_id: str = Query(...),
                          path: str = ""):
    """Get workspace file tree for a task."""
    task = None
    if project:
        task = task_engine.get_task(project, task_id)
    else:
        for candidate in task_engine.list_all_tasks():
            if str(candidate.get("id")) == task_id:
                task = candidate
                project = str(candidate.get("project", ""))
                break
    if not task:
        raise HTTPException(404, "Task not found")
    if not task.get("current_account_id"):
        raise HTTPException(400, "Task has no active account")

    acc = account_pool.get_account(task["current_account_id"])
    if not acc:
        raise HTTPException(404, "Account not found")

    data = await noc.get_file_tree(
        task.get("current_runtime_host", acc.get("runtime_host", "")),
        task.get("current_project_token", acc.get("project_token", "")),
        acc["auth_token"], path
    )
    return {"success": True, "data": data}


@router.get("/file/content")
async def skill_file_content(project: str | None = Query(None),
                             task_id: str = Query(...),
                             path: str = Query(...)):
    """Get current workspace file content for a task."""
    from backend.api.files import _resolve_task_runtime, _serialize_content
    if project:
        _, acc, runtime_host, project_token = _resolve_task_runtime(project, task_id)
    else:
        task = None
        for candidate in task_engine.list_all_tasks():
            if str(candidate.get("id")) == task_id:
                task = candidate
                project = str(candidate.get("project", ""))
                break
        if not task or not project:
            raise HTTPException(404, "Task not found")
        _, acc, runtime_host, project_token = _resolve_task_runtime(project, task_id)

    content_bytes = await noc.get_file_content(runtime_host, project_token, acc["auth_token"], path)
    return _serialize_content(content_bytes)
