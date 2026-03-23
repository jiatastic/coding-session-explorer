"""Session-level token totals: Codex rollout usage events or rough estimates."""

from __future__ import annotations

import json
from typing import Any

from core.models import MessageRole, Session

CodexTokenTotals = tuple[int, int, int, int | None]


def _as_int(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value, 10)
        except ValueError:
            return 0
    return 0


def extract_codex_token_usage_from_lines(lines: list[str]) -> CodexTokenTotals | None:
    """Last token_count event in rollout JSONL: input, output, total, context_window."""
    last_info: dict[str, Any] | None = None
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict) or obj.get("type") != "event_msg":
            continue
        pl = obj.get("payload")
        if not isinstance(pl, dict) or pl.get("type") != "token_count":
            continue
        inf = pl.get("info")
        if isinstance(inf, dict):
            last_info = inf

    if not last_info:
        return None

    tu = last_info.get("total_token_usage")
    if not isinstance(tu, dict):
        return None

    inp = _as_int(tu.get("input_tokens")) + _as_int(tu.get("cached_input_tokens"))
    out = _as_int(tu.get("output_tokens")) + _as_int(tu.get("reasoning_output_tokens"))
    total = _as_int(tu.get("total_tokens"))
    if total <= 0:
        total = inp + out
    ctx_raw = last_info.get("model_context_window")
    ctx: int | None
    try:
        ctx = int(ctx_raw) if ctx_raw is not None else None
    except (TypeError, ValueError):
        ctx = None

    return (inp, out, total, ctx)


def fill_estimated_token_fields(session: Session) -> None:
    """Rough ~4 chars per token, split by message role (no API)."""
    if session.tokens_total is not None:
        return
    inp = out = 0
    for m in session.messages:
        approx = max(0, len(m.content) // 4)
        if m.role in (MessageRole.USER, MessageRole.SYSTEM, MessageRole.TOOL):
            inp += approx
        else:
            out += approx
    total = inp + out
    if total <= 0:
        return
    session.tokens_input = inp
    session.tokens_output = out
    session.tokens_total = total
    session.tokens_estimated = True


def apply_session_token_stats(session: Session, rollout_lines: list[str] | None) -> None:
    """Prefer Codex usage; otherwise estimate from messages."""
    session.tokens_estimated = False
    if rollout_lines:
        parsed = extract_codex_token_usage_from_lines(rollout_lines)
        if parsed is not None:
            inp, out, total, ctx = parsed
            session.tokens_input = inp
            session.tokens_output = out
            session.tokens_total = total
            session.tokens_context_window = ctx
            return
    fill_estimated_token_fields(session)
