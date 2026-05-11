"""Shared SSE frame parsing utilities."""

from __future__ import annotations

import json
from typing import Any, AsyncIterable, AsyncIterator


async def parse_sse_frames(lines: AsyncIterable[Any]) -> AsyncIterator[tuple[str, str]]:
    """Yield `(event_name, data_text)` frames from a raw SSE line stream."""
    event_name = "message"
    data_lines: list[str] = []

    async for raw_line in lines:
        if raw_line is None:
            continue
        line = str(raw_line)
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip() or "message"
            continue
        if line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())
            continue
        if line.strip():
            data_lines.append(line)
            continue

        if data_lines:
            yield event_name, "\n".join(data_lines)
            data_lines.clear()
        event_name = "message"

    if data_lines:
        yield event_name, "\n".join(data_lines)


async def parse_sse_payloads(lines: AsyncIterable[Any]) -> AsyncIterator[tuple[str, Any]]:
    """Yield `(event_name, payload)` frames, decoding JSON payloads when possible."""
    async for event_name, data_text in parse_sse_frames(lines):
        payload: Any = data_text
        try:
            payload = json.loads(data_text)
        except Exception:
            payload = data_text
        yield event_name, payload


__all__ = ["parse_sse_frames", "parse_sse_payloads"]
