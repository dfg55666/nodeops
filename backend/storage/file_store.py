"""
File-based storage layer.
All persistent data lives as JSON/MD files under DATA_DIR.
"""
import json
import os
import asyncio
from pathlib import Path
from datetime import datetime, timezone

DATA_DIR = Path(os.environ.get("NODEOPS_DATA_DIR", Path(__file__).parent.parent.parent / "data"))

_locks: dict[str, asyncio.Lock] = {}


def _get_lock(path: str) -> asyncio.Lock:
    if path not in _locks:
        _locks[path] = asyncio.Lock()
    return _locks[path]


def ensure_data_dir():
    """Create data directory structure if missing."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "projects").mkdir(exist_ok=True)

    # Default config
    config_path = DATA_DIR / "config.json"
    if not config_path.exists():
        write_json(config_path, {
            "poll_interval_running": 5,
            "poll_interval_idle": 30,
            "idle_timeout": 120,
            "max_default_loops": 10,
        })

    # Default accounts
    accounts_path = DATA_DIR / "accounts.json"
    if not accounts_path.exists():
        write_json(accounts_path, [])


def read_json(path: Path) -> dict | list:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {} if path.suffix == ".json" else []


def write_json(path: Path, data: dict | list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


async def read_json_async(path: Path) -> dict | list:
    async with _get_lock(str(path)):
        return read_json(path)


async def write_json_async(path: Path, data: dict | list):
    async with _get_lock(str(path)):
        write_json(path, data)


def append_md(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(content)


async def append_md_async(path: Path, content: str):
    async with _get_lock(str(path)):
        append_md(path, content)


def read_md(path: Path) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Convenience paths
def accounts_path() -> Path:
    return DATA_DIR / "accounts.json"


def config_path() -> Path:
    return DATA_DIR / "config.json"


def project_dir(project_name: str) -> Path:
    return DATA_DIR / "projects" / project_name


def project_json(project_name: str) -> Path:
    return project_dir(project_name) / "project.json"


def task_json(project_name: str, task_id: str) -> Path:
    return project_dir(project_name) / "tasks" / f"{task_id}.json"


def tasks_dir(project_name: str) -> Path:
    return project_dir(project_name) / "tasks"


def repo_dir(project_name: str) -> Path:
    """
    Resolve repo directory for a project.
    Priority:
      1) project.json.local_repo_path (if configured)
      2) default managed path: data/projects/<name>/repo
    """
    pj = read_json(project_json(project_name))
    if isinstance(pj, dict):
        raw_local = str(pj.get("local_repo_path") or "").strip()
        if raw_local:
            p = Path(raw_local).expanduser()
            if not p.is_absolute():
                p = (project_dir(project_name) / p).resolve()
            return p
    return project_dir(project_name) / "repo"


def session_md_path(project_name: str, task_id: str, account_email: str, session_index: int) -> Path:
    # account_email is kept in the function signature for backward compatibility
    # with existing call sites, but session files are now stored flat:
    #   .nodeops/<task_id>/session-<n>.md
    return repo_dir(project_name) / ".nodeops" / task_id / f"session-{session_index}.md"
