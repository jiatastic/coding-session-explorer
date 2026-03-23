"""Local-only secrets (OpenAI API key). Env OPENAI_API_KEY always wins over disk."""

from __future__ import annotations

import json
import os
from typing import Any, Literal

from core.config import DATA_DIR

SECRETS_PATH = DATA_DIR / "secrets.json"


def _load_secrets_file() -> dict[str, Any]:
    if not SECRETS_PATH.is_file():
        return {}
    try:
        raw = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def get_stored_openai_api_key() -> str | None:
    """Key from secrets.json only (no env)."""
    key = str(_load_secrets_file().get("openai_api_key", "")).strip()
    return key or None


def get_openai_api_key() -> str | None:
    """Effective key: OPENAI_API_KEY env first, then secrets.json."""
    env = os.getenv("OPENAI_API_KEY", "").strip()
    if env:
        return env
    return get_stored_openai_api_key()


def openai_key_source() -> Literal["env", "file", "none"]:
    if os.getenv("OPENAI_API_KEY", "").strip():
        return "env"
    if get_stored_openai_api_key():
        return "file"
    return "none"


def set_stored_openai_api_key(key: str | None) -> None:
    """Write or remove openai_api_key in secrets.json. Does not touch process env."""
    SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = _load_secrets_file()
    cleaned = (key or "").strip()
    if cleaned:
        data["openai_api_key"] = cleaned
    else:
        data.pop("openai_api_key", None)
    if data:
        SECRETS_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        try:
            SECRETS_PATH.chmod(0o600)
        except OSError:
            pass
    elif SECRETS_PATH.is_file():
        SECRETS_PATH.unlink()
