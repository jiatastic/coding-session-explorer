from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def isolated_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from core import config as cfg

    data = tmp_path / "coding-sessions-data"
    data.mkdir()
    cfg_path = data / "config.toml"
    monkeypatch.setattr(cfg, "DATA_DIR", data)
    monkeypatch.setattr(cfg, "CONFIG_PATH", cfg_path)
    return data


def test_get_server_settings_from_toml(isolated_config_dir: Path) -> None:
    from core import config as cfg

    cfg.CONFIG_PATH.write_text(
        "[server]\nstrict_port = true\nport = 9001\n",
        encoding="utf-8",
    )
    s = cfg.get_server_settings()
    assert s["strict_port"] is True
    assert s["port"] == 9001
    assert s["host"] == "127.0.0.1"


def test_get_server_settings_env_strict_overrides_toml(
    isolated_config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core import config as cfg

    cfg.CONFIG_PATH.write_text("[server]\nstrict_port = true\n", encoding="utf-8")
    monkeypatch.setenv("SESS_TUI_STRICT_PORT", "false")
    s = cfg.get_server_settings()
    assert s["strict_port"] is False
