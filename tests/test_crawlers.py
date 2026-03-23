from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from core.crawlers import ClaudeCrawler, CodexCrawler, CursorCrawler
from core.crawlers import cursor as cursor_crawler
from core.models import SourceTool


def _with_fake_home(monkeypatch: Any, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))


def _fixture_path(name: str) -> Path:
    return Path(__file__).parent / "fixtures" / name


def test_claude_crawler_parses_summary_and_messages(tmp_path: Path, monkeypatch: Any) -> None:
    _with_fake_home(monkeypatch, tmp_path)

    source = Path(os.environ["HOME"]) / ".claude" / "transcripts" / "session.jsonl"
    source.parent.mkdir(parents=True)
    source.write_text(
        _fixture_path("claude/transcript.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
    )

    crawler = ClaudeCrawler()
    session = crawler.parse(str(source))

    assert session is not None
    assert session.source == SourceTool.CLAUDE
    assert session.title == "claude-fixture-project · Claude auth troubleshooting"
    assert session.message_count == 3
    assert session.project_path == "/tmp/claude-fixture-project"
    assert len(session.messages) == 3
    assert session.messages[0].role.value == "user"
    assert session.tokens_total is not None and session.tokens_total > 0
    assert session.tokens_estimated is True


def test_codex_crawler_modern_rollout_format(tmp_path: Path, monkeypatch: Any) -> None:
    _with_fake_home(monkeypatch, tmp_path)

    source = (
        Path(os.environ["HOME"])
        / ".codex"
        / "sessions"
        / "2026"
        / "03"
        / "22"
        / "modern.jsonl"
    )
    source.parent.mkdir(parents=True)
    source.write_text(
        _fixture_path("codex/session_modern.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
    )

    crawler = CodexCrawler()
    session = crawler.parse(str(source))

    assert session is not None
    assert session.id == "codex-modern-beta"
    assert session.project_path == "/tmp/codex-modern"
    assert session.message_count == 5
    assert [m.role.value for m in session.messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
        "assistant",
    ]
    assert "Hello from event_msg" in session.messages[0].content
    assert "Assistant structured reply" in session.messages[3].content
    assert session.tokens_input == 150
    assert session.tokens_output == 210
    assert session.tokens_total == 360
    assert session.tokens_context_window == 128000
    assert session.tokens_estimated is False


def test_codex_crawler_uses_first_user_as_title(tmp_path: Path, monkeypatch: Any) -> None:
    _with_fake_home(monkeypatch, tmp_path)

    source = (
        Path(os.environ["HOME"]) / ".codex" / "sessions" / "2026" / "03" / "22" / "session.jsonl"
    )
    source.parent.mkdir(parents=True)
    source.write_text(
        _fixture_path("codex/session.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
    )

    crawler = CodexCrawler()
    session = crawler.parse(str(source))

    assert session is not None
    assert session.source == SourceTool.CODEX
    assert session.id == "codex-session-alpha"
    assert session.title == "codex-project · How can I search for sessions quickly?"
    assert session.message_count == 2
    assert session.project_path == "/tmp/codex-project"
    assert session.tokens_total is not None and session.tokens_total > 0
    assert session.tokens_estimated is True


def test_codex_crawler_discovers_homes_archived_codex_home_and_project_tree(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _with_fake_home(monkeypatch, tmp_path)
    home = Path(os.environ["HOME"])
    fx = _fixture_path("codex/session.jsonl").read_text(encoding="utf-8")
    fx_modern = _fixture_path("codex/session_modern.jsonl").read_text(encoding="utf-8")

    g = home / ".codex" / "sessions" / "2026" / "03" / "22" / "g.jsonl"
    g.parent.mkdir(parents=True)
    g.write_text(fx, encoding="utf-8")

    arch = home / ".codex" / "archived_sessions" / "archived.jsonl"
    arch.parent.mkdir(parents=True)
    arch.write_text(fx_modern, encoding="utf-8")

    alt = tmp_path / "override_codex_home"
    alt.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(alt))
    e = alt / "sessions" / "from_env.jsonl"
    e.parent.mkdir(parents=True)
    e.write_text(fx, encoding="utf-8")

    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    p = repo / ".codex" / "sessions" / "project.jsonl"
    p.parent.mkdir(parents=True)
    p.write_text(fx, encoding="utf-8")
    monkeypatch.chdir(repo / "pkg")

    found = set(CodexCrawler().discover())
    assert str(g.resolve()) in found
    assert str(arch.resolve()) in found
    assert str(e.resolve()) in found
    assert str(p.resolve()) in found


def test_cursor_crawler_indexes_metadata_even_with_bad_blob(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _with_fake_home(monkeypatch, tmp_path)

    home = Path(os.environ["HOME"])
    db_path = home / ".cursor" / "chats" / "hash" / "store.db"
    db_path.parent.mkdir(parents=True)

    proj_dir = tmp_path / "cursor-ws-proj"
    proj_dir.mkdir()
    ws_file = (
        cursor_crawler._cursor_user_data_root() / "workspaceStorage" / "hash" / "workspace.json"
    )
    ws_file.parent.mkdir(parents=True, exist_ok=True)
    ws_file.write_text(
        json.dumps({"folder": proj_dir.resolve().as_uri()}),
        encoding="utf-8",
    )

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE meta (key TEXT, value TEXT)")
        conn.execute("CREATE TABLE blobs (key TEXT, value BLOB)")

        meta_json = _fixture_path("cursor/meta.json").read_text(encoding="utf-8")
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            ("0", meta_json.encode("utf-8").hex()),
        )

        good_blob = json.dumps(
            {"role": "user", "content": "first blob", "timestamp": 1700000001000}
        ).encode("utf-8")
        conn.execute(
            "INSERT INTO blobs (key, value) VALUES (?, ?)", ("1", sqlite3.Binary(good_blob))
        )
        conn.execute(
            "INSERT INTO blobs (key, value) VALUES (?, ?)", ("2", sqlite3.Binary(b"not-json"))
        )
        conn.commit()
    finally:
        conn.close()

    crawler = CursorCrawler()
    session = crawler.parse(str(db_path))

    assert session is not None
    assert session.source == SourceTool.CURSOR
    assert session.id == "cursor-session-alpha"
    assert session.title == "cursor-ws-proj · Cursor Fixture Session"
    assert session.message_count == 2
    assert len(session.messages) == 1
    assert session.messages[0].content == "first blob"
    assert session.project_path == str(proj_dir.resolve())


def test_cursor_crawler_discovers_and_parses_agent_transcripts(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _with_fake_home(monkeypatch, tmp_path)

    home = Path(os.environ["HOME"])
    transcript = (
        home
        / ".cursor"
        / "projects"
        / "-tmp-fix-proj"
        / "agent-transcripts"
        / "sess.jsonl"
    )
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        _fixture_path("cursor/agent-transcript.jsonl").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    crawler = CursorCrawler()
    paths = crawler.discover()
    assert str(transcript.resolve()) in paths

    session = crawler.parse(str(transcript))
    assert session is not None
    assert session.source == SourceTool.CURSOR
    assert session.id == hashlib.sha256(str(transcript.resolve()).encode()).hexdigest()
    assert session.project_path == "/tmp/fix/proj"
    assert session.message_count == 2
    assert session.messages[0].content == "Transcript user question"
