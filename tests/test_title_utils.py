from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from core.title_utils import (
    finalize_session_title,
    is_agents_md_instruction_opening,
    is_generic_session_name,
    primary_from_user_messages,
    refined_session_title,
    with_project_prefix,
)


def test_refined_title_leaves_normal_text_unchanged() -> None:
    t = refined_session_title(
        primary="Fix login bug",
        project_path="/tmp/p",
        source_path=Path("/x/y/z.jsonl"),
        created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
    )
    assert t == "Fix login bug"


def test_refined_title_rewrites_agents_md_boilerplate() -> None:
    primary = "# AGENTS.md instructions for /Users/me/Documents/GitHub/api_v2-feat-pri\nmore"
    out = refined_session_title(
        primary=primary,
        project_path=None,
        source_path=Path("/rollout.jsonl"),
        created_at=datetime(2026, 3, 22, 15, 30, tzinfo=UTC),
    )
    assert "api_v2-feat-pri" in out
    assert "AGENTS" in out
    assert "2026-03-22" in out


def test_is_agents_md_instruction_opening() -> None:
    assert is_agents_md_instruction_opening("# AGENTS.md instructions for /tmp/foo")
    assert not is_agents_md_instruction_opening("hello")


def test_primary_skips_low_signal_then_uses_substance() -> None:
    out = primary_from_user_messages(
        ["hi", "ok", "Fix OAuth redirect loop"],
        fallback="fallback-stem",
    )
    assert out == "Fix OAuth redirect loop"


def test_with_project_prefix_inserts_repo_name() -> None:
    assert with_project_prefix("Fix bug", "/Users/me/api_v2") == "api_v2 · Fix bug"


def test_with_project_prefix_skips_when_already_present() -> None:
    assert with_project_prefix("api_v2 schema change", "/Users/me/api_v2") == "api_v2 schema change"


def test_finalize_session_title_chain() -> None:
    t = finalize_session_title(
        primary="Investigate timeout",
        project_path="/tmp/checkout-svc",
        source_path=Path("/x/y/z.jsonl"),
        created_at=datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
    )
    assert t == "checkout-svc · Investigate timeout"


def test_is_generic_session_name() -> None:
    assert is_generic_session_name("New Chat")
    assert is_generic_session_name("cursor session")
    assert not is_generic_session_name("Implement rate limiting")
