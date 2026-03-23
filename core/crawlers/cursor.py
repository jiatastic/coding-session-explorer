from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from core.crawlers.base import BaseCrawler
from core.models import Message, MessageRole, Session, SourceTool


def _message_id(session_id: str, index: int) -> str:
    return hashlib.sha256(f"{session_id}:{index}".encode()).hexdigest()


def _parse_time(raw: object) -> datetime | None:
    if not isinstance(raw, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(int(raw) / 1000, tz=UTC)
    except (OSError, OverflowError, TypeError, ValueError):
        return None


def _decode_hex_json(raw: object) -> dict[str, object]:
    value = raw
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        raw_bytes = value
    elif isinstance(value, str):
        if not value:
            raise ValueError("empty payload")
        if all(ch in "0123456789abcdefABCDEF" for ch in value.strip()):
            raw_bytes = bytes.fromhex(value)
        else:
            raw_bytes = value.encode("utf-8")
    else:
        raw_bytes = str(value).encode("utf-8") if value is not None else b""

    try:
        parsed = json.loads(raw_bytes.decode("utf-8"))
    except Exception:
        raise

    if not isinstance(parsed, dict):
        raise ValueError("non-object payload")
    return parsed


class CursorCrawler(BaseCrawler):
    def discover(self) -> list[str]:
        base = Path.home() / ".cursor" / "chats"
        return [str(p) for p in base.glob("**/store.db")]

    def parse(self, path: str) -> Session | None:
        source_path = Path(path)
        if not source_path.exists() or source_path.is_dir():
            return None

        conn = sqlite3.connect(source_path.as_posix())
        try:
            rows = conn.execute("SELECT key, value FROM meta").fetchall()
            meta_payload: dict[str, object] | None = None
            for key, value in rows:
                if str(key) != "0":
                    continue
                try:
                    meta_payload = _decode_hex_json(value)
                except Exception as exc:  # noqa: BLE001
                    print(f"[warn] cannot decode cursor meta {path}: {exc}")
                    return None
                break

            if not meta_payload:
                return None

            session_id = str(meta_payload.get("agentId") or "")
            if not session_id:
                return None

            session_title = str(meta_payload.get("name") or "Cursor Session")
            created_at = _parse_time(meta_payload.get("createdAt")) or datetime.fromtimestamp(
                source_path.stat().st_mtime, tz=UTC
            )

            message_payloads = conn.execute("SELECT key, value FROM blobs").fetchall()
            message_count = len(message_payloads)
            parsed_messages: list[tuple[str, str, datetime | None]] = []

            for _blob_key, raw_blob in message_payloads:
                try:
                    decoded = _decode_hex_json(raw_blob)
                except Exception as exc:  # noqa: BLE001
                    print(f"[warn] cursor blob decode failed for {path}: {exc}")
                    continue

                if isinstance(decoded, dict):
                    role = str(
                        decoded.get("role") or decoded.get("type") or MessageRole.ASSISTANT.value
                    )
                    if role not in {m.value for m in MessageRole}:
                        role = MessageRole.ASSISTANT.value
                    content = str(decoded.get("content") or "").strip()
                elif isinstance(decoded, str):
                    role = MessageRole.ASSISTANT.value
                    content = decoded.strip()
                else:
                    continue

                if not content:
                    continue
                parsed_messages.append(
                    (
                        role,
                        content,
                        _parse_time(
                            decoded.get("timestamp") if isinstance(decoded, dict) else None
                        ),
                    )
                )

            session = Session(
                id=session_id,
                source=SourceTool.CURSOR,
                project_path=None,
                title=session_title,
                created_at=created_at,
                updated_at=max(
                    created_at, datetime.fromtimestamp(source_path.stat().st_mtime, tz=UTC)
                ),
                message_count=message_count,
                raw_path=str(source_path),
                messages=[],
            )

            for index, (role, content, ts) in enumerate(parsed_messages):
                session.messages.append(
                    Message(
                        id=_message_id(session_id, index),
                        session_id=session.id,
                        role=MessageRole(role),
                        content=content,
                        timestamp=ts,
                    )
                )

            return session
        finally:
            conn.close()
