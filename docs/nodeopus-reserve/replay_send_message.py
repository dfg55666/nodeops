"""
Minimal replay for NodeOps CreateOS backend (captured from createos.nodeops.network UI).

Usage (PowerShell):
  $env:NODEOPS_BASE_URL="https://quirky-pasteur7-374631.syra.nodeops.app"
  $env:NODEOPS_SESSION_ID="ses_..."
  $env:NODEOPS_PROJECT_TOKEN="<x-project-token jwt>"
  python docs/nodeopus-reserve/replay_send_message.py "hi"

Notes:
  - This script intentionally does NOT hardcode tokens.
  - The capture file with real headers/bodies is in docs/nodeopus-reserve/capture/capture_nodeops_send_2.json.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict

import requests


def _env(name: str, default: str | None = None) -> str:
    v = os.environ.get(name)
    if v is None:
        if default is None:
            raise SystemExit(f"Missing env var: {name}")
        return default
    return v


def main() -> None:
    base_url = _env("NODEOPS_BASE_URL").rstrip("/")
    session_id = _env("NODEOPS_SESSION_ID")
    project_token = _env("NODEOPS_PROJECT_TOKEN")

    provider_id = os.environ.get("NODEOPS_MODEL_PROVIDER_ID", "openrouter")
    model_id = os.environ.get("NODEOPS_MODEL_ID", "anthropic/claude-opus-4.6")

    # You can override system prompt, but CreateOS UI always sends one.
    system_prompt = os.environ.get(
        "NODEOPS_SYSTEM",
        "You are in BUILD MODE. Follow these rules strictly.",
    )

    text = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else "hi"

    url = f"{base_url}/session/{session_id}/message"
    payload: Dict[str, Any] = {
        "model": {"providerID": provider_id, "modelID": model_id},
        "system": system_prompt,
        "parts": [{"type": "text", "text": text}],
    }

    headers = {
        "Content-Type": "application/json",
        "x-project-token": project_token,
        # Keeping Referer in case the backend enforces it.
        "Referer": "https://createos.nodeops.network/",
    }

    r = requests.post(url, headers=headers, json=payload, timeout=120)
    print("status:", r.status_code)
    r.raise_for_status()

    data = r.json()
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


