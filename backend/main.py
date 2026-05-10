"""
NodeOps Manager — FastAPI backend entry point.
"""
import logging
import signal
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Support both:
#   1) uvicorn backend.main:app   (cwd = nodeops/)
#   2) uvicorn main:app           (cwd = nodeops/backend/)
THIS_DIR = Path(__file__).resolve().parent
PARENT_DIR = THIS_DIR.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.storage.file_store import ensure_data_dir
from backend.services.nodeops_client import close_client
from backend.api import accounts, projects, tasks, sessions, files, events, skills, register

# ─── Logging ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ─── Lifespan ───────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("NodeOps Manager starting up...")
    ensure_data_dir()
    logger.info("Data directory initialized")
    yield
    # Shutdown
    logger.info("Shutting down...")
    await close_client()
    logger.info("HTTP client closed")


# ─── App ────────────────────────────────────────────────────────────
app = FastAPI(
    title="NodeOps Manager",
    description="Multi-account NodeOps management platform with task loop system",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routes ─────────────────────────────────────────────────────────
app.include_router(accounts.router)
app.include_router(projects.router)
app.include_router(tasks.router)
app.include_router(sessions.router)
app.include_router(files.router)
app.include_router(events.router)
app.include_router(skills.router)
app.include_router(register.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/overview")
def overview():
    """Dashboard overview data."""
    from backend.services import account_pool, task_engine
    from backend.storage.file_store import DATA_DIR

    all_accounts = account_pool.list_accounts()
    all_tasks = task_engine.list_all_tasks()

    projects_path = DATA_DIR / "projects"
    project_count = sum(1 for p in projects_path.iterdir() if p.is_dir()) if projects_path.exists() else 0

    return {
        "success": True,
        "data": {
            "accounts_total": len(all_accounts),
            "accounts_available": sum(1 for a in all_accounts if a.get("status") == "available" and not a.get("locked_by_task")),
            "accounts_exhausted": sum(1 for a in all_accounts if a.get("status") == "exhausted"),
            "projects_total": project_count,
            "tasks_total": len(all_tasks),
            "tasks_running": sum(1 for t in all_tasks if t.get("status") == "running"),
            "tasks_completed": sum(1 for t in all_tasks if t.get("status") == "completed"),
        }
    }


# ─── Graceful shutdown ──────────────────────────────────────────────
def _handle_sigterm(*_):
    logger.info("Received SIGTERM, shutting down...")
    sys.exit(0)

signal.signal(signal.SIGTERM, _handle_sigterm)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
