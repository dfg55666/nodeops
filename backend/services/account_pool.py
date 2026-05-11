"""
Account pool — manage multiple NodeOps accounts.
Handles selection, locking, releasing, and status tracking.
"""
import uuid
import logging
from datetime import datetime, timezone
from backend.storage.file_store import (
    accounts_path, read_json, write_json, now_iso,
)

logger = logging.getLogger(__name__)


def _load() -> list[dict]:
    data = read_json(accounts_path())
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _save(accounts: list[dict]):
    write_json(accounts_path(), accounts)


def list_accounts() -> list[dict]:
    """Return all accounts (with tokens masked for display)."""
    accounts = _load()
    result = []
    for acc in accounts:
        safe = {**acc}
        if safe.get("auth_token"):
            safe["auth_token_preview"] = safe["auth_token"][:20] + "..."
            safe["auth_token"] = ""
        if safe.get("project_token"):
            safe["project_token_preview"] = safe["project_token"][:20] + "..."
            safe["project_token"] = ""
        result.append(safe)
    return result


def get_account(account_id: str) -> dict | None:
    accounts = _load()
    for acc in accounts:
        if acc["id"] == account_id:
            return acc
    return None


def get_account_by_email(email: str) -> dict | None:
    accounts = _load()
    for acc in accounts:
        if acc["email"] == email:
            return acc
    return None


def add_account(email: str, auth_token: str = "",
                deployment_id: str = "", runtime_host: str = "",
                project_token: str = "") -> dict:
    """Add a new account to the pool."""
    accounts = _load()

    # Check duplicate email
    for acc in accounts:
        if acc["email"] == email:
            raise ValueError(f"Account with email {email} already exists")

    account = {
        "id": str(uuid.uuid4()),
        "email": email,
        "auth_token": auth_token,
        "token_expires_at": None,
        "deployment_id": deployment_id,
        "runtime_host": runtime_host,
        "project_token": project_token,
        "credits_remaining": 0,
        "status": "available",
        "locked_by_task": None,
        "last_used_at": None,
        "created_at": now_iso(),
    }
    accounts.append(account)
    _save(accounts)
    logger.info(f"Added account: {email}")
    return account


def update_account(account_id: str, updates: dict) -> dict | None:
    """Update account fields."""
    accounts = _load()
    for i, acc in enumerate(accounts):
        if acc["id"] == account_id:
            accounts[i] = {**acc, **updates}
            _save(accounts)
            return accounts[i]
    return None


def delete_account(account_id: str) -> bool:
    accounts = _load()
    new_accounts = [a for a in accounts if a["id"] != account_id]
    if len(new_accounts) == len(accounts):
        return False
    _save(new_accounts)
    return True


def acquire_account(exclude_ids: list[str] | None = None,
                    task_id: str | None = None) -> dict | None:
    """Get the best available account and lock it.

    Selection priority:
      1. status == 'available' and not locked
      2. highest credits_remaining
      3. exclude already-used accounts (by exclude_ids)
    """
    accounts = _load()
    exclude = set(exclude_ids or [])

    candidates = [
        acc for acc in accounts
        if acc["status"] == "available"
        and acc["id"] not in exclude
        and acc.get("locked_by_task") is None
        and acc.get("auth_token")  # must have a token
    ]

    if not candidates:
        return None

    # Pick the one with most credits
    candidates.sort(key=lambda a: a.get("credits_remaining", 0), reverse=True)
    chosen = candidates[0]

    # Lock it
    chosen["locked_by_task"] = task_id
    chosen["last_used_at"] = now_iso()
    _save(accounts)

    logger.info(f"Acquired account {chosen['email']} for task {task_id}")
    return chosen


def release_account(account_id: str, exhausted: bool = False):
    """Release an account lock. Optionally mark as exhausted."""
    accounts = _load()
    for acc in accounts:
        if acc["id"] == account_id:
            acc["locked_by_task"] = None
            if exhausted:
                acc["status"] = "exhausted"
            break
    _save(accounts)
    logger.info(f"Released account {account_id}, exhausted={exhausted}")


def release_task_locks(task_id: str, keep_account_id: str | None = None) -> int:
    """Release every account lock held by a task.

    Returns number of released locks.
    """
    keep_id = str(keep_account_id or "").strip()
    tid = str(task_id or "").strip()
    if not tid:
        return 0

    accounts = _load()
    released = 0
    changed = False
    for acc in accounts:
        if str(acc.get("locked_by_task") or "").strip() != tid:
            continue
        if keep_id and str(acc.get("id") or "").strip() == keep_id:
            continue
        acc["locked_by_task"] = None
        released += 1
        changed = True
    if changed:
        _save(accounts)
        logger.info("Released %s stale locks for task %s", released, tid)
    return released


def mark_account_status(account_id: str, status: str):
    """Set account status (available / exhausted / disabled)."""
    update_account(account_id, {"status": status})


def update_credits(account_id: str, credits: float):
    """Update cached credit balance."""
    update_account(account_id, {"credits_remaining": credits})


def get_available_count() -> int:
    """Count of available, unlocked accounts."""
    accounts = _load()
    return sum(
        1 for a in accounts
        if a["status"] == "available" and a.get("locked_by_task") is None
    )
