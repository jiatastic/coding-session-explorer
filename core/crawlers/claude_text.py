from __future__ import annotations

from typing import Any


def pick_dominant_cwd(lines: list[dict[str, Any]]) -> str | None:
    """Most frequent non-empty cwd on user/assistant lines (Claude Code JSONL)."""
    counts: dict[str, int] = {}
    for raw in lines:
        if raw.get("type") not in ("user", "assistant"):
            continue
        cwd = raw.get("cwd")
        if isinstance(cwd, str):
            c = cwd.strip()
            if c:
                counts[c] = counts.get(c, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: kv[1])[0]


def text_from_claude_user_line(raw: dict[str, Any]) -> str:
    msg = raw.get("message")
    if isinstance(msg, dict):
        c = msg.get("content")
        if isinstance(c, str) and c.strip():
            return c.strip()
    c = raw.get("content")
    if isinstance(c, str) and c.strip():
        return c.strip()
    return ""


def text_from_claude_assistant_line(raw: dict[str, Any]) -> str:
    msg = raw.get("message")
    if isinstance(msg, dict):
        c = msg.get("content")
        if isinstance(c, list):
            parts: list[str] = []
            for block in c:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text" and isinstance(block.get("text"), str):
                    t = block["text"].strip()
                    if t:
                        parts.append(t)
                elif btype == "tool_use":
                    name = block.get("name")
                    if isinstance(name, str) and name:
                        parts.append(f"[{name}]")
            return "\n".join(parts).strip()
        if isinstance(c, str) and c.strip():
            return c.strip()
    c = raw.get("content")
    if isinstance(c, str) and c.strip():
        return c.strip()
    return ""
