from __future__ import annotations

from datetime import UTC, datetime

from core.models import Message, MessageRole, Session, SourceTool
from core.token_stats import (
    apply_session_token_stats,
    extract_codex_token_usage_from_lines,
)


def test_extract_codex_token_usage_from_rollout_lines() -> None:
    lines = [
        '{"type":"event_msg","payload":{"type":"token_count","info":'
        '{"total_token_usage":{"input_tokens":10,"cached_input_tokens":5,'
        '"output_tokens":3,"reasoning_output_tokens":2,"total_tokens":20},'
        '"model_context_window":100000}}}'
    ]
    got = extract_codex_token_usage_from_lines(lines)
    assert got is not None
    inp, out, total, ctx = got
    assert inp == 15
    assert out == 5
    assert total == 20
    assert ctx == 100000


def test_apply_session_token_stats_codex_prefers_usage_event() -> None:
    lines = [
        '{"type":"event_msg","payload":{"type":"token_count","info":'
        '{"total_token_usage":{"input_tokens":1,"output_tokens":2,"total_tokens":3},'
        '"model_context_window":8000}}}'
    ]
    session = Session(
        id="x",
        source=SourceTool.CODEX,
        project_path=None,
        title="t",
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
        message_count=0,
        raw_path="/x",
        messages=[
            Message(
                id="m",
                session_id="x",
                role=MessageRole.USER,
                content="a" * 400,
            )
        ],
    )
    apply_session_token_stats(session, lines)
    assert session.tokens_total == 3
    assert session.tokens_context_window == 8000
    assert session.tokens_estimated is False


def test_apply_session_token_stats_estimate_from_roles() -> None:
    session = Session(
        id="y",
        source=SourceTool.CLAUDE,
        project_path=None,
        title="t",
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
        message_count=2,
        raw_path="/y",
        messages=[
            Message(id="a", session_id="y", role=MessageRole.USER, content="aaaa"),
            Message(id="b", session_id="y", role=MessageRole.ASSISTANT, content="bbbb"),
        ],
    )
    apply_session_token_stats(session, None)
    assert session.tokens_input == 1
    assert session.tokens_output == 1
    assert session.tokens_total == 2
    assert session.tokens_estimated is True
