from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from core import db
from core import search as search_module
from core.crawlers import cursor as cursor_crawler
from core.indexer import index_all
from core.models import SourceTool


def _with_fake_home(monkeypatch: Any, tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))


def _fixture_path(name: str) -> Path:
    return Path(__file__).parent / "fixtures" / name


def _seed_data(home: str) -> None:
    base = os.fspath(home)

    claude = os.path.join(base, ".claude", "transcripts", "fixture.jsonl")
    os.makedirs(os.path.dirname(claude), exist_ok=True)
    _copy_fixture(_fixture_path("claude/transcript.jsonl"), claude)

    codex = os.path.join(base, ".codex", "sessions", "2026", "03", "22", "fixture.jsonl")
    os.makedirs(os.path.dirname(codex), exist_ok=True)
    _copy_fixture(_fixture_path("codex/session.jsonl"), codex)

    cursor = os.path.join(base, ".cursor", "chats", "hash", "store.db")
    cursor_dir = os.path.dirname(cursor)
    os.makedirs(cursor_dir, exist_ok=True)

    proj_dir = Path(base) / "cursor-ws-proj"
    proj_dir.mkdir(parents=True, exist_ok=True)
    ws_file = (
        cursor_crawler._cursor_user_data_root() / "workspaceStorage" / "hash" / "workspace.json"
    )
    ws_file.parent.mkdir(parents=True, exist_ok=True)
    ws_file.write_text(
        json.dumps({"folder": proj_dir.resolve().as_uri()}),
        encoding="utf-8",
    )

    conn = sqlite3.connect(cursor)
    try:
        conn.execute("CREATE TABLE meta (key TEXT, value TEXT)")
        conn.execute("CREATE TABLE blobs (key TEXT, value BLOB)")
        meta_payload = json.dumps(
            {
                "agentId": "cursor-session-alpha",
                "name": "Cursor Session",
                "createdAt": 1700000200000,
                "lastUsedModel": "gpt-4o-mini",
            }
        )
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            ("0", meta_payload.encode("utf-8").hex()),
        )
        conn.execute(
            "INSERT INTO blobs (key, value) VALUES (?, ?)",
            (
                "1",
                sqlite3.Binary(
                    b'{"role":"user","content":"Cursor search message","timestamp":1700000201000}'
                ),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _copy_fixture(source: Path, destination: str) -> None:
    content = source.read_text(encoding="utf-8")
    with open(destination, "w", encoding="utf-8") as output:
        output.write(content)


def test_end_to_end_indexing_and_fulltext_search(monkeypatch: Any, tmp_path: Path) -> None:
    _with_fake_home(monkeypatch, tmp_path)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    _seed_data(os.environ["HOME"])

    monkeypatch.setattr("core.indexer.embed_session", lambda _: 0)

    db.init_db()
    stats = index_all(force=True)

    assert stats["new_sessions"] == 3
    sessions = db.list_sessions(limit=10)
    assert len(sessions) == 3

    found = search_module.fulltext_search("vector", n_results=5)
    assert any(item.session_id for item in found)
    assert {item.source for item in found} == {SourceTool.CODEX}

    codex_hits = [item for item in found if item.source == SourceTool.CODEX]
    assert codex_hits
