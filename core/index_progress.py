"""Thread-safe indexing progress for CLI, API, and TUI polling."""

from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_state: dict[str, Any] = {
    "running": False,
    "phase": "idle",
    "crawler": None,
    "current": 0,
    "total": 0,
    "detail": None,
    "stats": None,
    "error": None,
}


def reset_running() -> None:
    with _lock:
        _state.update(
            {
                "running": True,
                "phase": "running",
                "crawler": None,
                "current": 0,
                "total": 0,
                "detail": None,
                "stats": None,
                "error": None,
            }
        )


def update(
    *,
    crawler: str | None = None,
    current: int | None = None,
    total: int | None = None,
    detail: str | None = None,
) -> None:
    with _lock:
        if crawler is not None:
            _state["crawler"] = crawler
        if current is not None:
            _state["current"] = current
        if total is not None:
            _state["total"] = total
        if detail is not None:
            _state["detail"] = detail


def finish(stats: dict[str, int]) -> None:
    with _lock:
        _state.update(
            {
                "running": False,
                "phase": "done",
                "stats": dict(stats),
                "error": None,
            }
        )


def fail(message: str) -> None:
    with _lock:
        _state.update(
            {
                "running": False,
                "phase": "error",
                "error": message,
            }
        )


def snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "running": bool(_state["running"]),
            "phase": str(_state["phase"]),
            "crawler": _state["crawler"],
            "current": int(_state["current"]),
            "total": int(_state["total"]),
            "detail": _state["detail"],
            "stats": dict(_state["stats"]) if _state["stats"] else None,
            "error": _state["error"],
        }


def is_running() -> bool:
    with _lock:
        return bool(_state["running"])
