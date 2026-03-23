from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from core.crawlers import ClaudeCrawler, CodexCrawler, CursorCrawler
from core.models import SourceTool


def _with_fake_home(monkeypatch: Any, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))


def _fixture_path(name: str) -> Path:
    return Path(__file__).parent / "fixtures" / name


def test_claude_crawler_parses_summary_and_messages(tmp_path: Path, monkeypatch: Any) -> None:
    _with_fake_home(monkeypatch, tmp_path)

    source = tmp_path / "home" / ".claude" / "transcripts" / "session.jsonl"
    source.parent.mkdir(parents=True)
    source.write_text(
        _fixture_path("claude/transcript.jsonl").read_text(encoding="utf-8"), encoding="utf-8"
    )

    crawler = ClaudeCrawler()
    session = crawler.parse(str(source))

    assert session is not None
    assert session.source == SourceTool.CLAUDE
    assert session.title == "Claude auth troubleshooting"
    assert session.message_count == 3
    assert session.project_path is None
    assert len(session.messages) == 3
    assert session.messages[0].role.value == "user"


def test_codex_crawler_uses_first_user_as_title(tmp_path: Path, monkeypatch: Any) -> None:
    _with_fake_home(monkeypatch, tmp_path)

    source = (
        tmp_path / "home" / ".codex" / "sessions" / "2026" / "03" / "22" / "session.jsonl"
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
    assert session.title == "How can I search for sessions quickly?"
    assert session.message_count == 2


def test_cursor_crawler_indexes_metadata_even_with_bad_blob(
    tmp_path: Path, monkeypatch: Any
) -> None:
    _with_fake_home(monkeypatch, tmp_path)

    home = tmp_path / "home"
    db_path = home / ".cursor" / "chats" / "hash" / "store.db"
    db_path.parent.mkdir(parents=True)

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
    assert session.title == "Cursor Fixture Session"
    assert session.message_count == 2
    assert len(session.messages) == 1
    assert session.messages[0].content == "first blob"
