"""Task management routes."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.services import task_engine
from backend.services import account_pool

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class ModelRef(BaseModel):
    providerID: str = "openrouter"
    modelID: str


class CreateTaskRequest(BaseModel):
    project: str
    mode: str = "auto"  # auto | oneshot
    message: str | None = None
    prompt: str | None = None
    model: ModelRef | None = None
    max_loops: int = 10
    task_id: str | None = None


class UpdateTaskRequest(BaseModel):
    message: str | None = None
    mode: str | None = None
    model: ModelRef | None = None
    max_loops: int | None = None
    status: str | None = None


@router.get("")
def list_all_tasks():
    tasks = [_decorate_task(t) for t in task_engine.list_all_tasks()]
    return {"success": True, "data": tasks}


@router.get("/project/{project_name}")
def list_project_tasks(project_name: str):
    tasks = [_decorate_task(t) for t in task_engine.list_tasks(project_name)]
    return {"success": True, "data": tasks}


@router.get("/{project_name}/{task_id}")
def get_task(project_name: str, task_id: str):
    task = task_engine.get_task(project_name, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return {"success": True, "data": _decorate_task(task)}


@router.post("")
def create_task(req: CreateTaskRequest):
    try:
        message = (req.message or req.prompt or "").strip()
        if not message:
            raise ValueError("message or prompt is required")
        task = task_engine.create_task(
            project_name=req.project,
            mode=req.mode,
            message=message,
            model=req.model.model_dump() if req.model else None,
            max_loops=req.max_loops,
            task_id=req.task_id,
        )
        return {"success": True, "data": _decorate_task(task)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/{project_name}/{task_id}")
def update_task(project_name: str, task_id: str, req: UpdateTaskRequest):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    task = task_engine.update_task(project_name, task_id, updates)
    if not task:
        raise HTTPException(404, "Task not found")
    return {"success": True, "data": _decorate_task(task)}


@router.delete("/{project_name}/{task_id}")
def delete_task(project_name: str, task_id: str):
    if not task_engine.delete_task(project_name, task_id):
        raise HTTPException(404, "Task not found")
    return {"success": True}


@router.post("/{project_name}/{task_id}/start")
async def start_task(project_name: str, task_id: str):
    try:
        await task_engine.start_task(project_name, task_id)
        return {"success": True, "data": {"status": "running"}}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{project_name}/{task_id}/cancel")
async def cancel_task(project_name: str, task_id: str):
    await task_engine.cancel_task(project_name, task_id)
    return {"success": True, "data": {"status": "canceled"}}


@router.post("/{project_name}/{task_id}/sessions/empty")
async def create_empty_session(project_name: str, task_id: str):
    try:
        data = await task_engine.create_empty_session(project_name, task_id)
        return {"success": True, "data": data}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{project_name}/{task_id}/messages")
def get_task_messages(project_name: str, task_id: str):
    """Get cached messages for an active task."""
    messages = task_engine.get_task_messages(task_id)
    return {"success": True, "data": messages}


def _decorate_task(task: dict) -> dict:
    """Attach frontend-friendly derived fields without mutating stored task."""
    item = {**task}

    accounts = []
    acc_id = item.get("current_account_id")
    if acc_id:
        acc = account_pool.get_account(acc_id)
        if acc:
            accounts.append({
                "id": acc.get("id"),
                "email": acc.get("email"),
                "status": acc.get("status"),
                "credits": acc.get("credits_remaining"),
            })
    item["accounts"] = accounts
    item["current_loop"] = item.get("loop_count", 0)
    item["progress"] = item.get("loops", [])
    return item
