"""Serialize SQLite + Chroma writes during parallel indexing (multi-thread safe)."""

from __future__ import annotations

import threading

writer_lock = threading.Lock()
