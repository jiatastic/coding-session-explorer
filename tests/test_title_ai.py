from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch

from core import db
from core.models import Message, MessageRole, Session, SourceTool
from core.title_ai import _clean_model_title, maybe_ai_session_title, suggest_ai_title


def _fake_home(monkeypatch: Any, tmp_path: Any) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))


def test_clean_model_title() -> None:
    assert _clean_model_title('  "Fix login"  ') == "Fix login"
    assert _clean_model_title("# OAuth redirect") == "OAuth redirect"
    assert _clean_model_title("ab") is None


def test_suggest_ai_title_disabled(monkeypatch: Any) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    with patch("core.title_ai.get_summarization_settings", return_value={"title_ai": False}):
        session = Session(
            id="s1",
            source=SourceTool.CODEX,
            project_path=None,
            title="x",
            created_at=datetime.now(tz=UTC),
            updated_at=datetime.now(tz=UTC),
            message_count=1,
            raw_path="/tmp/x",
            messages=[
                Message(
                    id="m1",
                    session_id="s1",
                    role=MessageRole.USER,
                    content="hello world",
                    timestamp=None,
                )
            ],
        )
        assert suggest_ai_title(session) is None


def test_maybe_ai_session_title_updates_db(monkeypatch: Any, tmp_path: Any) -> None:
    _fake_home(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    db.init_db()

    session = Session(
        id="sid-ai",
        source=SourceTool.CLAUDE,
        project_path="/Users/me/proj",
        title="Heuristic title",
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
        message_count=1,
        raw_path="/tmp/y",
        messages=[
            Message(
                id="mid1",
                session_id="sid-ai",
                role=MessageRole.USER,
                content="Implement OAuth",
                timestamp=None,
            )
        ],
    )
    assert db.upsert_session(session) is True

    with patch("core.title_ai.get_summarization_settings", return_value={"title_ai": True}):
        with patch("core.title_ai.suggest_ai_title", return_value="OAuth callback handling"):
            assert maybe_ai_session_title("sid-ai") is True

    loaded = db.get_session("sid-ai")
    assert loaded is not None
    assert "OAuth callback handling" in (loaded.title or "")
    assert "proj" in (loaded.title or "")
