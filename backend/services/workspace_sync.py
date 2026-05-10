"""
Workspace sync — download files from NodeOps workspace and git push.
"""
import asyncio
import logging
import os
import shutil
from pathlib import Path
from backend.services import nodeops_client as noc
from backend.storage.file_store import repo_dir

logger = logging.getLogger(__name__)


def _extract_tree_entries(tree: object) -> list[dict]:
    if isinstance(tree, list):
        return [entry for entry in tree if isinstance(entry, dict)]
    if isinstance(tree, dict):
        raw_entries = tree.get("files") or tree.get("entries") or tree.get("children") or []
        if isinstance(raw_entries, list):
            return [entry for entry in raw_entries if isinstance(entry, dict)]
    return []


def _entry_path(entry: dict, parent_path: str) -> str:
    raw_path = str(entry.get("path") or "").strip().lstrip("/")
    if raw_path:
        return raw_path
    name = str(entry.get("name") or "").strip().lstrip("/")
    if not name:
        return ""
    return f"{parent_path}/{name}".lstrip("/") if parent_path else name


def _is_dir_entry(entry: dict) -> bool:
    entry_type = str(entry.get("type", "file")).lower()
    return entry_type in ("directory", "dir", "folder", "tree")


def _download_concurrency() -> int:
    raw = str(os.environ.get("NODEOPS_SYNC_FILE_CONCURRENCY", "4")).strip()
    try:
        parsed = int(raw)
    except ValueError:
        parsed = 4
    return max(1, min(16, parsed))


async def _collect_workspace_files(
    runtime_host: str,
    project_token: str,
    auth_token: str,
    base_path: str = "",
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
                    runtime_host, project_token, auth_token, entry_path
                )
            )
        else:
            file_paths.append(entry_path)

    return file_paths


async def _detect_remote_base_path(
    runtime_host: str,
    project_token: str,
    auth_token: str,
    project_name: str,
) -> str:
    """
    Detect the remote workspace base path to sync from.
    Priority:
      1) folder named like local repo directory name
      2) folder named like project_name
      3) workspace root
    """
    target = repo_dir(project_name)
    local_repo_name = target.name.strip().lower()
    project_name_norm = str(project_name or "").strip().lower()
    candidates = [name for name in (local_repo_name, project_name_norm) if name]

    if not candidates:
        return ""

    root_tree = await noc.get_file_tree(runtime_host, project_token, auth_token, "")
    entries = _extract_tree_entries(root_tree)
    for entry in entries:
        if entry.get("ignored") or not _is_dir_entry(entry):
            continue
        entry_name = str(entry.get("name") or "").strip().lower()
        if entry_name and entry_name in candidates:
            matched = _entry_path(entry, "")
            if matched:
                return matched
    return ""


async def download_workspace(runtime_host: str, project_token: str,
                             auth_token: str, target_dir: Path,
                             base_path: str = ""):
    """Download workspace files from NodeOps into target_dir.

    Uses /file?path= for directory listing and /file/content?path= for file content.
    File content downloads are bounded-concurrency to balance speed and 429 risk.
    """
    logger.info(
        "Downloading workspace from %s to %s (base_path=%s)",
        runtime_host,
        target_dir,
        base_path or "/",
    )
    file_paths = await _collect_workspace_files(
        runtime_host, project_token, auth_token, base_path
    )

    if not file_paths:
        return {"total": 0, "downloaded": 0, "failed": 0}

    sem = asyncio.Semaphore(_download_concurrency())
    failures: list[str] = []

    async def _fetch_one(path: str):
        async with sem:
            try:
                content = await noc.get_file_content(
                    runtime_host, project_token, auth_token, path
                )
                file_path = target_dir / path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, "wb") as f:
                    f.write(content)
                logger.debug("Downloaded: %s", path)
            except Exception as e:
                failures.append(path)
                logger.warning("Failed to download %s: %s", path, e)

    await asyncio.gather(*(_fetch_one(path) for path in file_paths))
    return {
        "total": len(file_paths),
        "downloaded": len(file_paths) - len(failures),
        "failed": len(failures),
    }


async def sync_workspace_to_repo(runtime_host: str, project_token: str,
                                 auth_token: str, project_name: str):
    """Download workspace files and overwrite the local repo."""
    target = repo_dir(project_name)
    if not target.exists():
        logger.error(f"Repo dir does not exist: {target}")
        return False

    # Download into a temp dir first, then overwrite.
    # If workspace root has a folder matching local repo folder name,
    # sync from that subfolder to avoid nested repo artifacts.
    import tempfile
    remote_base_path = ""
    try:
        remote_base_path = await _detect_remote_base_path(
            runtime_host, project_token, auth_token, project_name
        )
    except Exception as e:
        logger.warning("Remote base-path detection failed, fallback to root: %s", e)
    if remote_base_path:
        logger.info("Detected remote repo folder: %s", remote_base_path)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        summary = await download_workspace(
            runtime_host, project_token, auth_token, tmp_path, remote_base_path
        )
        logger.info(
            "Workspace download summary: total=%s downloaded=%s failed=%s",
            summary.get("total", 0),
            summary.get("downloaded", 0),
            summary.get("failed", 0),
        )

        copy_root = tmp_path / remote_base_path if remote_base_path else tmp_path
        if remote_base_path and not copy_root.exists():
            logger.warning(
                "Detected remote base path %s not found in temp tree, fallback to workspace root",
                remote_base_path,
            )
            copy_root = tmp_path

        # Overwrite repo files (skip .git and .nodeops)
        for item in copy_root.rglob("*"):
            if item.is_file():
                rel = item.relative_to(copy_root)
                if rel.parts and rel.parts[0] in {".git", ".nodeops"}:
                    continue
                dest = target / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)
                logger.debug(f"Synced: {rel}")

    logger.info(f"Workspace synced to {target}")
    return True


async def git_push(project_name: str, commit_message: str) -> str | None:
    """Git add, commit, and push in the repo directory.

    Returns commit hash on success, None on failure.
    """
    cwd = str(repo_dir(project_name))

    if not os.path.exists(os.path.join(cwd, ".git")):
        logger.error(f"Not a git repo: {cwd}")
        return None

    try:
        # git add -A
        proc = await asyncio.create_subprocess_exec(
            "git", "add", "-A",
            cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.wait()

        # Check if there's anything to commit
        proc = await asyncio.create_subprocess_exec(
            "git", "status", "--porcelain",
            cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        if not stdout.strip():
            logger.info("No changes to commit")
            return "no-changes"

        # git commit
        proc = await asyncio.create_subprocess_exec(
            "git", "commit", "-m", commit_message,
            cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error(f"git commit failed: {stderr.decode()}")
            return None

        # Get commit hash
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "HEAD",
            cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        commit_hash = stdout.decode().strip()

        # git push
        proc = await asyncio.create_subprocess_exec(
            "git", "push",
            cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error(f"git push failed: {stderr.decode()}")
            return None

        logger.info(f"Pushed commit {commit_hash}")
        return commit_hash

    except Exception as e:
        logger.error(f"Git operation failed: {e}")
        return None


async def git_clone(github_url: str, project_name: str) -> bool:
    """Clone a GitHub repo into the project's repo directory."""
    target = repo_dir(project_name)

    if target.exists() and os.path.exists(os.path.join(str(target), ".git")):
        logger.info(f"Repo already cloned: {target}")
        return True

    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "clone", github_url, str(target),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error(f"git clone failed: {stderr.decode()}")
            return False
        logger.info(f"Cloned {github_url} to {target}")
        return True
    except Exception as e:
        logger.error(f"git clone error: {e}")
        return False
