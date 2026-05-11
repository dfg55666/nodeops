"""Helpers for rebuilding session markdown snapshots."""

from __future__ import annotations


def build_session_messages_snapshot(
    raw: str,
    rows: list[dict],
    timestamp: str | None = None,
) -> str:
    marker = "## Messages"
    if marker in raw:
        idx = raw.find(marker)
        marker_end = raw.find("\n", idx)
        if marker_end == -1:
            header = raw.rstrip("\n") + "\n"
        else:
            header = raw[: marker_end + 1]
        if not header.endswith("\n\n"):
            header = header.rstrip("\n") + "\n\n"
    else:
        header = raw.rstrip("\n")
        if header:
            header += "\n\n"
        header += "## Messages\n\n"

    body_lines: list[str] = []
    for row in rows:
        role = str(row.get("role") or "").strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = str(row.get("content") or "").rstrip()
        if not content:
            continue
        tag = "Assistant" if role == "assistant" else "User"
        prefix = f"[{tag}] {timestamp}" if timestamp else f"[{tag}]"
        body_lines.append(f"{prefix}\n{content}\n\n")
    return header + "".join(body_lines)


__all__ = ["build_session_messages_snapshot"]
