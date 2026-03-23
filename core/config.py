from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DATA_DIR = Path.home() / ".coding-sessions"
CONFIG_PATH = DATA_DIR / "config.toml"

DEFAULT_CONFIG: dict[str, Any] = {
    "embedding": {
        "provider": "openai",
        "model": "text-embedding-3-small",
        "batch_size": 100,
    },
    "sources": {
        "claude": True,
        "codex": True,
        "cursor": True,
    },
    "server": {
        "host": "127.0.0.1",
        "port": 8000,
        "strict_port": False,
    },
    "summarization": {
        "enabled": True,
        "model": "gpt-4o-mini",
        "title_ai": False,
    },
}


def ensure_config() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_PATH.exists():
        return

    serialized = []
    for section, values in DEFAULT_CONFIG.items():
        serialized.append(f"[{section}]")
        for key, value in values.items():
            if isinstance(value, str):
                serialized.append(f'{key} = "{value}"')
            elif isinstance(value, bool):
                serialized.append(f"{key} = {str(value).lower()}")
            else:
                serialized.append(f"{key} = {value}")
        serialized.append("")

    CONFIG_PATH.write_text("\n".join(serialized), encoding="utf-8")


def load_config() -> dict[str, Any]:
    ensure_config()

    raw = CONFIG_PATH.read_bytes()
    loaded = tomllib.loads(raw.decode("utf-8"))
    if not isinstance(loaded, dict):
        return DEFAULT_CONFIG

    config = {**DEFAULT_CONFIG}
    for section, value in loaded.items():
        if isinstance(value, dict):
            merged = dict(config.get(section, {}))
            merged.update(value)
            config[section] = merged
        else:
            config[section] = value

    return config


def get_summarization_settings() -> dict[str, Any]:
    config = load_config()
    section = config.get("summarization", {})
    raw_enabled = os.getenv("SUMMARIZATION_ENABLED", str(section.get("enabled", True))).lower()
    enabled = raw_enabled not in ("0", "false", "no", "off")
    model = os.getenv("SUMMARIZATION_MODEL") or str(section.get("model", "gpt-4o-mini"))
    title_ai = bool(section.get("title_ai", False))
    env_title = os.getenv("TITLE_AI_ENABLED", "").strip().lower()
    if env_title in ("1", "true", "yes", "on"):
        title_ai = True
    if env_title in ("0", "false", "no", "off"):
        title_ai = False
    return {"enabled": enabled, "model": model, "title_ai": title_ai}


def get_server_settings() -> dict[str, Any]:
    config = load_config()
    section = config.get("server", {})
    strict = bool(section.get("strict_port", False))
    env_strict = os.getenv("SESS_TUI_STRICT_PORT", "").strip().lower()
    if env_strict in ("1", "true", "yes", "on"):
        strict = True
    if env_strict in ("0", "false", "no", "off"):
        strict = False
    try:
        port = int(section.get("port", 8000))
    except (TypeError, ValueError):
        port = 8000
    return {"host": str(section.get("host", "127.0.0.1")), "port": port, "strict_port": strict}


def get_embedding_settings() -> dict[str, Any]:
    config = load_config()
    settings = config.get("embedding", {})
    provider = os.getenv("EMBEDDING_PROVIDER") or str(settings.get("provider", "openai"))
    model = os.getenv("EMBEDDING_MODEL") or str(settings.get("model", "text-embedding-3-small"))
    try:
        batch_size = int(settings.get("batch_size", 100))
    except (TypeError, ValueError):
        batch_size = 100
    return {
        "provider": provider,
        "model": model,
        "batch_size": batch_size,
    }
