# Deploymoment (Deployment) Code Map (2026-05-10)

This document maps all current code paths that create a new NodeOps deployment ("deploymoment"), so another engineer can take over quickly.

## 1) Entry Points

- Manual empty session API entry:
  - `backend/api/tasks.py:104` -> `create_empty_session(...)`
  - Calls service-layer empty session flow in `task_engine`.

- Chat send API entry:
  - `backend/api/sessions.py:68` -> `send_message(...)`
  - This is the main path that can force-create fresh deployment + fresh session before sending.

## 2) Service-Layer Deployment Creation

- Empty session flow:
  - `backend/services/task_engine.py:267` -> `create_empty_session(...)`
  - Runtime preparation call:
    - `backend/services/task_engine.py:314`
    - Uses `ensure_task_runtime_for_send(..., force_new=False)` at `backend/services/task_engine.py:319`
  - Meaning: empty session now prefers reusing current runtime context; it does not force fresh deployment every time.

- Task loop flow:
  - `backend/services/task_engine.py:449`
  - Uses `ensure_task_runtime_for_send(..., force_new=True)` at `backend/services/task_engine.py:454`
  - Meaning: task loop enforces fresh deployment per loop.

- Shared runtime/deployment helper:
  - `backend/services/task_engine.py:622` -> `ensure_task_runtime_for_send(...)`
  - `backend/services/task_engine.py:643` reuse branch:
    - If runtime exists and `force_new` is false, returns current runtime.
  - `backend/services/task_engine.py:646` creation branch:
    - Calls `_ensure_deployment(...)`

- Fresh deployment implementation:
  - `backend/services/task_engine.py:657` -> `_ensure_deployment(...)`
  - Actual deployment create call:
    - `backend/services/task_engine.py:693` -> `noc.create_deployment(auth_token, prompt=create_prompt)`

## 3) Chat Send Fresh-Bootstrap Path

- Send orchestration:
  - `backend/api/sessions.py:68` -> `send_message(...)`
  - Task-bound mode detection:
    - `backend/api/sessions.py:80` -> `task_bound_send = bool(req.project_name and req.task_id)`

- Task-bound send bootstrap:
  - `backend/api/sessions.py:88`
  - Calls `_bootstrap_fresh_runtime_session_for_task_send(...)`

- Fresh bootstrap function:
  - `backend/api/sessions.py:374` -> `_bootstrap_fresh_runtime_session_for_task_send(...)`
  - Force fresh deployment call:
    - `backend/api/sessions.py:385`
    - `force_new=True` at `backend/api/sessions.py:390`
  - Fresh session creation:
    - `backend/api/sessions.py` inside same function via `noc.create_session(...)`
  - Task current runtime/session update:
    - In same function via `task_engine.update_task(...)`
  - Local session markdown session-id rewrite:
    - `backend/api/sessions.py:417`
    - Helper `backend/api/sessions.py:443` -> `_replace_local_session_id_header(...)`

## 4) Runtime HTTP Client (Actual Upstream Calls)

- Runtime request header/token routing:
  - `backend/services/nodeops_client.py:124` -> `_runtime_request(...)`
  - Session-root token branch:
    - `backend/services/nodeops_client.py:138-139`

- Deployment create API:
  - `backend/services/nodeops_client.py:295` -> `create_deployment(...)`
  - Primary endpoint:
    - `/deployments/pi-agent` at `backend/services/nodeops_client.py:303`
  - Fallback endpoint:
    - `/deployments` fallback log at `backend/services/nodeops_client.py:313`

## 5) Retry/Compatibility Logic for Runtime Fluctuation

- Send-time retry loop:
  - `backend/api/sessions.py:124` -> `send_attempts = 3 if task_bound_send else 1`
  - Retry condition:
    - `backend/api/sessions.py:141-143`

- Fresh bootstrap retry loop:
  - `backend/api/sessions.py:374` function
  - Retry decision:
    - `backend/api/sessions.py:426`

- Transient error classifier:
  - `backend/api/sessions.py:531` -> `_is_transient_upstream_error(...)`
  - Includes keywords for 503/connect/reset/timeout and runtime-propagation style 404/403 session errors.

## 6) Frontend Send Payload Linkage

- Composer send action:
  - `frontend/src/components/SessionView.jsx:840` -> calls `api.sendSessionMessage(...)`
  - Includes task context:
    - `frontend/src/components/SessionView.jsx:846` -> `project_name`
    - `frontend/src/components/SessionView.jsx:847` -> `task_id`
  - Session id source used by composer:
    - `frontend/src/components/SessionView.jsx:1348` -> `effectiveSessionId = headerSessionId || selectedSessionId`
  - Composer mount:
    - `frontend/src/components/SessionView.jsx:1502`

## 7) Practical Notes for Handoff

- If you want "send always fresh deployment/session", edit in:
  - `backend/api/sessions.py` (`send_message` + `_bootstrap_fresh_runtime_session_for_task_send`)

- If you want empty session to also always fresh deployment:
  - Change `force_new=False` back to `force_new=True` at:
    - `backend/services/task_engine.py:319`

- If you want fewer retries or different transient classification:
  - `backend/api/sessions.py:124` (attempt count)
  - `backend/api/sessions.py:531` (classifier)

