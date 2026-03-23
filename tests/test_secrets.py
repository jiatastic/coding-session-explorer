"""Tests for ~/.coding-sessions-backed OpenAI key storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.secrets import (
    get_openai_api_key,
    get_stored_openai_api_key,
    openai_key_source,
    set_stored_openai_api_key,
)


@pytest.fixture
def secrets_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "secrets.json"
    monkeypatch.setattr("core.secrets.SECRETS_PATH", path)
    return path


def test_no_key(secrets_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert get_openai_api_key() is None
    assert openai_key_source() == "none"


def test_stored_key(secrets_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    set_stored_openai_api_key("sk-local-test")
    assert get_stored_openai_api_key() == "sk-local-test"
    assert get_openai_api_key() == "sk-local-test"
    assert openai_key_source() == "file"


def test_env_overrides_file(secrets_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    set_stored_openai_api_key("sk-file")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    assert get_openai_api_key() == "sk-env"
    assert openai_key_source() == "env"
    assert get_stored_openai_api_key() == "sk-file"


def test_clear_stored(secrets_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    set_stored_openai_api_key("sk-x")
    set_stored_openai_api_key(None)
    assert get_stored_openai_api_key() is None
    assert get_openai_api_key() is None
