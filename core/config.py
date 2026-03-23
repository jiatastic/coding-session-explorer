from __future__ import annotations

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


def get_openai_api_key() -> str | None:
    """Read optional API key from ~/.coding-sessions/config.toml (not from repo .env files)."""
    emb = load_config().get("embedding", {})
    if not isinstance(emb, dict):
        return None
    for key in ("openai_api_key", "api_key"):
        raw = emb.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def get_embedding_settings() -> dict[str, Any]:
    config = load_config()
    settings = config.get("embedding", {})
    provider = str(settings.get("provider", "openai"))
    model = str(settings.get("model", "text-embedding-3-small"))
    try:
        batch_size = int(settings.get("batch_size", 100))
    except (TypeError, ValueError):
        batch_size = 100
    return {
        "provider": provider,
        "model": model,
        "batch_size": batch_size,
    }
