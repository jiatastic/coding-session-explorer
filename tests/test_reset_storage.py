from __future__ import annotations

from pathlib import Path
from typing import Any

from core import db


def _fake_home(tmp_path: Path, monkeypatch: Any) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


def test_reset_index_storage_removes_db_and_chroma(tmp_path: Path, monkeypatch: Any) -> None:
    _fake_home(tmp_path, monkeypatch)
    root = Path.home() / ".coding-sessions"
    root.mkdir(parents=True)
    db_file = root / "sessions.db"
    db_file.write_text("sqlite", encoding="utf-8")
    wal = root / "sessions.db-wal"
    wal.write_bytes(b"x")
    chroma = root / "chroma"
    chroma.mkdir()
    (chroma / "seg").write_text("y", encoding="utf-8")

    db.invalidate_engine()
    removed = db.reset_index_storage(remove_entire_data_dir=False)

    assert not db_file.exists()
    assert not wal.exists()
    assert not chroma.exists()
    assert root.is_dir()
    assert removed


def test_reset_index_storage_all_wipes_directory(tmp_path: Path, monkeypatch: Any) -> None:
    _fake_home(tmp_path, monkeypatch)
    root = Path.home() / ".coding-sessions"
    root.mkdir(parents=True)
    (root / "config.toml").write_text("x", encoding="utf-8")

    db.invalidate_engine()
    removed = db.reset_index_storage(remove_entire_data_dir=True)

    assert not root.exists()
    assert removed


def test_reset_index_storage_noop_when_missing(tmp_path: Path, monkeypatch: Any) -> None:
    _fake_home(tmp_path, monkeypatch)
    db.invalidate_engine()
    assert db.reset_index_storage(remove_entire_data_dir=False) == []
    assert db.reset_index_storage(remove_entire_data_dir=True) == []
