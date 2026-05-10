"""Project management routes."""
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.storage.file_store import (
    project_dir, project_json, repo_dir,
    read_json, write_json, now_iso, DATA_DIR,
)
from backend.services import workspace_sync

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    name: str
    github_url: str = ""
    description: str = ""
    local_repo_path: str = ""


class UpdateProjectRequest(BaseModel):
    github_url: str | None = None
    description: str | None = None
    local_repo_path: str | None = None


@router.get("")
def list_projects():
    projects_path = DATA_DIR / "projects"
    if not projects_path.exists():
        return {"success": True, "data": []}

    projects = []
    for pdir in sorted(projects_path.iterdir()):
        if pdir.is_dir():
            pj = read_json(pdir / "project.json")
            if not isinstance(pj, dict):
                continue
            # Guard against corrupted wrapper format {path, content, encoding}
            if "content" in pj and "path" in pj and "name" not in pj:
                import json as _json
                try:
                    pj = _json.loads(pj["content"])
                    # Persist the fixed content
                    write_json(pdir / "project.json", pj)
                except Exception:
                    continue
            if not pj.get("name"):
                continue
            # Count tasks
            tasks_path = pdir / "tasks"
            task_count = len(list(tasks_path.glob("*.json"))) if tasks_path.exists() else 0
            pj["task_count"] = task_count
            pj["repo_path"] = str(repo_dir(pj.get("name", pdir.name)))
            projects.append(pj)
    return {"success": True, "data": projects}


@router.get("/{project_name}")
def get_project(project_name: str):
    pj = read_json(project_json(project_name))
    if not pj:
        raise HTTPException(404, "Project not found")
    pj["repo_path"] = str(repo_dir(project_name))
    return {"success": True, "data": pj}


@router.post("")
async def create_project(req: CreateProjectRequest):
    # Validate name
    name = req.name.strip().lower().replace(" ", "-")
    if not name:
        raise HTTPException(400, "Invalid project name")

    pdir = project_dir(name)
    if pdir.exists():
        raise HTTPException(400, f"Project '{name}' already exists")

    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "tasks").mkdir(exist_ok=True)

    project = {
        "name": name,
        "github_url": req.github_url,
        "description": req.description,
        "local_repo_path": req.local_repo_path.strip(),
        "created_at": now_iso(),
    }
    write_json(project_json(name), project)

    project["repo_path"] = str(repo_dir(name))

    return {"success": True, "data": project}


@router.put("/{project_name}")
def update_project(project_name: str, req: UpdateProjectRequest):
    pj_path = project_json(project_name)
    pj = read_json(pj_path)
    if not pj:
        raise HTTPException(404, "Project not found")

    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    pj.update(updates)
    write_json(pj_path, pj)
    pj["repo_path"] = str(repo_dir(project_name))
    return {"success": True, "data": pj}


@router.delete("/{project_name}")
def delete_project(project_name: str):
    pdir = project_dir(project_name)
    if not pdir.exists():
        raise HTTPException(404, "Project not found")

    import shutil
    shutil.rmtree(pdir)
    return {"success": True}


@router.post("/{project_name}/clone")
async def clone_repo(project_name: str):
    """Clone or re-clone the project's GitHub repo."""
    pj = read_json(project_json(project_name))
    if not pj:
        raise HTTPException(404, "Project not found")
    if not pj.get("github_url"):
        raise HTTPException(400, "No GitHub URL configured")

    # Safety: if a custom local repo path is configured, do not auto-delete/reclone.
    local_repo_path = str((pj or {}).get("local_repo_path") or "").strip()
    if local_repo_path:
        raise HTTPException(
            400,
            "Project uses local_repo_path; skip re-clone endpoint to avoid deleting local repo. Use git pull manually.",
        )

    # Remove existing managed repo dir if present
    rdir = repo_dir(project_name)
    if rdir.exists():
        import shutil
        shutil.rmtree(rdir)

    success = await workspace_sync.git_clone(pj["github_url"], project_name)
    if not success:
        raise HTTPException(500, "Failed to clone repository")

    return {"success": True}
