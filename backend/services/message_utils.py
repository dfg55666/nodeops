"""Shared message parsing utilities for NodeOps runtime payloads."""

from __future__ import annotations

import json
from typing import Any


def _to_text(value: Any, limit: int = 0) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        raw = json.dumps(value, ensure_ascii=False)
    else:
        raw = str(value)
    raw = raw.strip()
    if limit and len(raw) > limit:
        return raw[:limit] + "..."
    return raw


def extract_message_text(msg: dict) -> str:
    """Extract readable text from a runtime message object."""
    if isinstance(msg.get("content"), str):
        return msg["content"]

    parts = msg.get("parts", msg.get("content", []))
    if isinstance(parts, list):
        texts: list[str] = []
        for part in parts:
            if isinstance(part, str):
                plain = part.strip()
                if plain:
                    texts.append(plain)
                continue
            if not isinstance(part, dict):
                continue

            ptype = str(part.get("type") or "").strip().lower().replace("_", "-")
            if ptype == "text":
                txt = _to_text(part.get("text"))
                if txt:
                    texts.append(txt)
            elif ptype == "tool":
                invocation = part.get("toolInvocation")
                if not isinstance(invocation, dict):
                    invocation = {}

                name = _to_text(
                    invocation.get("toolName")
                    or invocation.get("tool_name")
                    or part.get("toolName")
                    or "tool"
                )
                state = str(invocation.get("state") or "").strip().lower()
                label = _to_text(invocation.get("label"))
                duration = invocation.get("durationMs")
                is_error = bool(invocation.get("isError", False))

                args_txt = _to_text(invocation.get("args"), limit=300)

                result_txt = ""
                result = invocation.get("result")
                if isinstance(result, dict):
                    result_content = result.get("content")
                    if isinstance(result_content, list):
                        result_parts: list[str] = []
                        for rc in result_content:
                            if isinstance(rc, dict):
                                rc_txt = _to_text(rc.get("text") or rc.get("content"))
                                if rc_txt:
                                    result_parts.append(rc_txt)
                            elif isinstance(rc, str):
                                rc_txt = rc.strip()
                                if rc_txt:
                                    result_parts.append(rc_txt)
                        result_txt = "\n".join([r for r in result_parts if r]).strip()
                    elif isinstance(result_content, str):
                        result_txt = result_content.strip()
                    if not result_txt:
                        result_txt = _to_text(result, limit=500)
                elif result is not None:
                    result_txt = _to_text(result, limit=500)

                header = f"[Tool: {name}]"
                if state:
                    header += f" [{state}]"
                if duration:
                    header += f" ({duration}ms)"
                if is_error:
                    header += " ERROR"

                lines = [header]
                if args_txt:
                    lines.append(args_txt)
                if result_txt:
                    lines.append(f"Result:\n{result_txt[:500]}")
                elif label:
                    lines.append(label)
                texts.append("\n".join([line for line in lines if line]))
            elif ptype == "tool-use":
                name = _to_text(
                    part.get("name") or part.get("toolName") or part.get("tool_name") or "tool"
                )
                inp = part.get("input")
                if inp is None:
                    inp = part.get("args")
                inp_txt = _to_text(inp, limit=200)
                if inp_txt:
                    texts.append(f"[Tool: {name}]\n{inp_txt}")
                else:
                    texts.append(f"[Tool: {name}]")
            elif ptype == "tool-result":
                name = _to_text(
                    part.get("name") or part.get("toolName") or part.get("tool_name") or "tool"
                )
                out = part.get("output")
                if out is None:
                    out = part.get("content")
                if out is None:
                    out = part.get("text")
                out_txt = _to_text(out, limit=300)
                if out_txt:
                    texts.append(f"[Tool Result: {name}]\n{out_txt}")
                else:
                    texts.append(f"[Tool Result: {name}]")
            elif ptype in {"step-finish", "step-start"}:
                continue
            else:
                fallback = _to_text(part.get("text") or part.get("content"))
                if fallback:
                    texts.append(f"[{ptype or 'part'}] {fallback}")

        joined = "\n\n".join([t for t in texts if str(t).strip()])
        if joined.strip():
            return joined

    info = msg.get("info")
    if isinstance(info, dict):
        err = info.get("error")
        if isinstance(err, dict):
            err_name = str(err.get("name") or "").strip()
            err_data = err.get("data")
            if isinstance(err_data, dict):
                msg_text = str(err_data.get("message") or "").strip()
                status_code = err_data.get("statusCode")
                if msg_text:
                    if status_code is not None and str(status_code).strip():
                        return f"[error:{status_code}] {msg_text}"
                    if err_name:
                        return f"[{err_name}] {msg_text}"
                    return msg_text
            if err_name:
                return f"[{err_name}]"

    return str(msg.get("content", msg.get("text", "")))


def extract_message_role(msg: dict) -> str:
    """Extract normalized role from runtime message payload."""
    role = msg.get("role")
    if role:
        return str(role).strip().lower()
    info = msg.get("info")
    if isinstance(info, dict):
        info_role = info.get("role")
        if info_role:
            return str(info_role).strip().lower()
    return "unknown"


def normalize_chat_role(role: str) -> str:
    normalized = str(role or "").strip().lower()
    if normalized in {"user", "assistant"}:
        return normalized
    if normalized == "unknown":
        return "assistant"
    return normalized


def normalize_messages(messages_data: Any) -> list[dict]:
    """Return the runtime message objects as a plain list."""
    if isinstance(messages_data, list):
        return [m for m in messages_data if isinstance(m, dict)]
    if isinstance(messages_data, dict):
        for key in ("messages", "data", "items"):
            value = messages_data.get(key)
            if isinstance(value, list):
                return [m for m in value if isinstance(m, dict)]
    return []


__all__ = [
    "extract_message_role",
    "extract_message_text",
    "normalize_chat_role",
    "normalize_messages",
]
