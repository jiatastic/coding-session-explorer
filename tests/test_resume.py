"""Tests for native CLI resume argv construction."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from core.models import Session, SourceTool
from core.resume import build_resume_command, format_resume_shell


def _session(**kwargs) -> Session:
    defaults = dict(
        id="sid",
        source=SourceTool.CODEX,
        project_path=None,
        repo_url=None,
        title="T",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 2, tzinfo=UTC),
        message_count=1,
        raw_path="/tmp/x.jsonl",
        summary=None,
        messages=[],
    )
    defaults.update(kwargs)
    return Session(**defaults)


def test_codex_resume_with_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SESS_RESUME_CODEX_BIN", raising=False)
    s = _session(
        source=SourceTool.CODEX,
        id="4557bbea-bceb-464a-8265-55005585cb4c",
        project_path="/repo/api",
    )
    cmd = build_resume_command(s)
    uid = "4557bbea-bceb-464a-8265-55005585cb4c"
    assert cmd.argv == ["codex", "resume", "-C", "/repo/api", uid]
    assert cmd.cwd is None


def test_codex_resume_bin_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESS_RESUME_CODEX_BIN", "/opt/codex")
    s = _session(source=SourceTool.CODEX, id="u1", project_path=None)
    cmd = build_resume_command(s)
    assert cmd.argv == ["/opt/codex", "resume", "u1"]


def test_cursor_resume_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SESS_RESUME_CURSOR_BIN", raising=False)
    s = _session(
        source=SourceTool.CURSOR,
        id="9ac15289-9e6f-47de-a304-6ccbfc1bac9b",
        project_path="/ws/proj",
    )
    cmd = build_resume_command(s)
    assert cmd.argv == [
        "agent",
        "--workspace",
        "/ws/proj",
        "--resume",
        "9ac15289-9e6f-47de-a304-6ccbfc1bac9b",
    ]


def test_cursor_resume_no_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SESS_RESUME_CURSOR_BIN", raising=False)
    s = _session(source=SourceTool.CURSOR, id="cid", project_path=None)
    cmd = build_resume_command(s)
    assert cmd.argv == ["agent", "--resume", "cid"]


def test_claude_continue_in_project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SESS_RESUME_CLAUDE_BIN", raising=False)
    s = _session(
        source=SourceTool.CLAUDE,
        project_path="/Users/me/app",
        raw_path="/Users/me/.claude/transcripts/foo.jsonl",
    )
    cmd = build_resume_command(s)
    assert cmd.argv == ["claude", "-c"]
    assert cmd.cwd == "/Users/me/app"
    assert "not Claude" in cmd.hint


def test_claude_resume_by_stem(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SESS_RESUME_CLAUDE_BIN", raising=False)
    s = _session(
        source=SourceTool.CLAUDE,
        project_path=None,
        raw_path="/home/u/.claude/transcripts/my-thread.jsonl",
        title=" · display title",
    )
    cmd = build_resume_command(s)
    assert cmd.argv == ["claude", "--resume", "my-thread"]


def test_format_resume_shell_cd() -> None:
    s = _session(
        source=SourceTool.CLAUDE,
        project_path="/tmp/a b",
    )
    line = format_resume_shell(s)
    assert line.startswith("cd ")
    assert "claude" in line
    assert "-c" in line
