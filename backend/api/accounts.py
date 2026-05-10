"""Account management routes."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.services import account_pool
from backend.services import nodeops_client as noc
from backend.services import credit_monitor

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


class AddAccountRequest(BaseModel):
    email: str
    auth_token: str = ""
    deployment_id: str = ""
    runtime_host: str = ""
    project_token: str = ""


class UpdateAccountRequest(BaseModel):
    email: str | None = None
    auth_token: str | None = None
    deployment_id: str | None = None
    runtime_host: str | None = None
    project_token: str | None = None
    status: str | None = None


class LoginRequest(BaseModel):
    email: str


class VerifyOTPRequest(BaseModel):
    email: str
    otp: str | None = None
    code: str | None = None


class RefreshRuntimeRequest(BaseModel):
    prompt: str = "init"
    create_session: bool = False
    session_title: str | None = None


@router.get("")
def list_accounts():
    return {"success": True, "data": account_pool.list_accounts()}


@router.get("/available-count")
def available_count():
    return {"success": True, "data": {"count": account_pool.get_available_count()}}


@router.get("/{account_id}")
def get_account(account_id: str):
    acc = account_pool.get_account(account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    return {"success": True, "data": acc}


@router.post("")
def add_account(req: AddAccountRequest):
    try:
        acc = account_pool.add_account(
            email=req.email,
            auth_token=req.auth_token,
            deployment_id=req.deployment_id,
            runtime_host=req.runtime_host,
            project_token=req.project_token,
        )
        return {"success": True, "data": acc}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/{account_id}")
def update_account(account_id: str, req: UpdateAccountRequest):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    acc = account_pool.update_account(account_id, updates)
    if not acc:
        raise HTTPException(404, "Account not found")
    return {"success": True, "data": acc}


@router.delete("/{account_id}")
def delete_account(account_id: str):
    if not account_pool.delete_account(account_id):
        raise HTTPException(404, "Account not found")
    return {"success": True}


@router.post("/{account_id}/unbind-task")
def unbind_task(account_id: str):
    """Clear task lock binding for an account."""
    acc = account_pool.get_account(account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    updated = account_pool.update_account(account_id, {"locked_by_task": None})
    if not updated:
        raise HTTPException(404, "Account not found")
    return {"success": True, "data": updated}


@router.post("/{account_id}/refresh-credits")
async def refresh_credits(account_id: str):
    """Refresh credit balance for an account."""
    acc = account_pool.get_account(account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    if not acc.get("auth_token"):
        raise HTTPException(400, "Account has no auth token")

    result = await credit_monitor.check_credits(acc["auth_token"], account_id)
    return {"success": True, "data": result}


@router.post("/{account_id}/refresh-runtime")
async def refresh_runtime(account_id: str, req: RefreshRuntimeRequest):
    """
    Force-create a fresh deployment and replace runtime token/host for account.
    Useful when old deployment accepts user message writes but no assistant output.
    """
    acc = account_pool.get_account(account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    if not acc.get("auth_token"):
        raise HTTPException(400, "Account has no auth token")

    prompt = str(req.prompt or "").strip() or "init"
    try:
        dep_payload = await noc.create_deployment(acc["auth_token"], prompt=prompt)
    except Exception as exc:
        raise HTTPException(502, f"Create deployment failed: {exc}")

    dep = dep_payload.get("data") if isinstance(dep_payload, dict) and isinstance(dep_payload.get("data"), dict) else dep_payload
    dep = dep if isinstance(dep, dict) else {}

    deployment_id = str(dep.get("id") or dep.get("deployment_id") or dep.get("deploymentId") or "").strip()
    runtime_host = str(
        dep.get("server_endpoint")
        or dep.get("runtimeHost")
        or dep.get("runtime_host")
        or dep.get("endpoint")
        or dep.get("host")
        or ""
    ).strip().rstrip("/")
    project_token = str(dep.get("token") or dep.get("project_token") or dep.get("projectToken") or "").strip()

    if not runtime_host or not project_token:
        raise HTTPException(502, f"Deployment response missing runtime/token: {dep_payload}")

    updates = {
        "deployment_id": deployment_id or acc.get("deployment_id") or "",
        "runtime_host": runtime_host,
        "project_token": project_token,
        "status": "available",
    }
    if "session_id" in acc:
        updates["session_id"] = None

    updated = account_pool.update_account(account_id, updates)
    if not updated:
        raise HTTPException(404, "Account not found after update")

    out: dict = {
        "deployment_id": updates["deployment_id"],
        "runtime_host": runtime_host,
        "project_token_preview": project_token[:20] + "...",
    }

    if req.create_session:
        try:
            session = await noc.create_session(
                runtime_host,
                project_token,
                acc["auth_token"],
                title=req.session_title or "manual-refresh-session",
            )
            session_id = (
                str(session.get("id") or "")
                or str(session.get("sessionId") or "")
                or str(session.get("session_id") or "")
            ).strip()
            if session_id:
                account_pool.update_account(account_id, {"session_id": session_id})
                out["session_id"] = session_id
        except Exception as exc:
            out["session_error"] = str(exc)

    return {"success": True, "data": out}


@router.post("/login")
async def login(req: LoginRequest):
    """Trigger OTP email for an account."""
    result = await noc.login(req.email)
    return {"success": True, "data": result}


@router.post("/verify-otp")
async def verify_otp(req: VerifyOTPRequest):
    """Verify OTP and get auth token."""
    otp = (req.otp or req.code or "").strip()
    if not otp:
        raise HTTPException(400, "otp is required")

    result = await noc.verify_otp(req.email, otp)
    # Auto-save token to account if it exists
    acc = account_pool.get_account_by_email(req.email)
    if not acc:
        try:
            acc = account_pool.add_account(email=req.email)
        except ValueError:
            acc = account_pool.get_account_by_email(req.email)
    if acc:
        data = result.get("data", {}) if isinstance(result, dict) else {}
        token = (
            (result.get("token") if isinstance(result, dict) else None)
            or (result.get("auth_token") if isinstance(result, dict) else None)
            or (data.get("token") if isinstance(data, dict) else None)
            or (data.get("auth_token") if isinstance(data, dict) else None)
            or ""
        )
        if token:
            account_pool.update_account(acc["id"], {"auth_token": token})
    return {"success": True, "data": result}
