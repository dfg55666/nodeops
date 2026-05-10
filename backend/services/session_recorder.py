"""
Session recorder — writes SSE messages to .md files.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from backend.storage.file_store import (
    session_md_path, append_md, now_iso,
)

logger = logging.getLogger(__name__)


def init_session_file(project_name: str, task_id: str,
                      account_email: str, session_index: int,
                      nodeops_session_id: str):
    """Create a new session .md file with header."""
    path = session_md_path(project_name, task_id, account_email, session_index)
    path.parent.mkdir(parents=True, exist_ok=True)

    header = (
        f"# Session {session_index} - {task_id}\n"
        f"- Account: {account_email}\n"
        f"- NodeOps Session ID: {nodeops_session_id}\n"
        f"- Started: {now_iso()}\n"
        f"- End Reason: (in progress)\n"
        f"\n## Messages\n\n"
    )
    # Write fresh (overwrite if exists)
    with open(path, "w", encoding="utf-8") as f:
        f.write(header)

    logger.info(f"Initialized session file: {path}")
    return path


def append_message(project_name: str, task_id: str,
                   account_email: str, session_index: int,
                   role: str, content: str):
    """Append a message to the session .md file."""
    path = session_md_path(project_name, task_id, account_email, session_index)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    norm = str(role or "unknown").strip().lower()
    if norm == "assistant":
        role_tag = "Assistant"
    elif norm == "user":
        role_tag = "User"
    elif norm == "system":
        role_tag = "System"
    else:
        role_tag = "Unknown"
    text = str(content or "")
    entry = f"[{role_tag}] {timestamp}\n{text}\n\n"
    append_md(path, entry)


def append_raw_sse(project_name: str, task_id: str,
                   account_email: str, session_index: int,
                   sse_data: str):
    """Append raw SSE data to the session file."""
    path = session_md_path(project_name, task_id, account_email, session_index)
    append_md(path, sse_data + "\n")


def finalize_session(project_name: str, task_id: str,
                     account_email: str, session_index: int,
                     end_reason: str):
    """Update the session file header with end info."""
    path = session_md_path(project_name, task_id, account_email, session_index)
    if not path.exists():
        return

    content = path.read_text(encoding="utf-8")
    content = content.replace(
        "- End Reason: (in progress)",
        f"- Ended: {now_iso()}\n- End Reason: {end_reason}"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"Finalized session: {path} reason={end_reason}")
