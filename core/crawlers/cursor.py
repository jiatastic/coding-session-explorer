from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from core.crawlers.base import BaseCrawler
from core.models import Message, MessageRole, Session, SourceTool
from core.title_utils import (
    finalize_session_title,
    is_generic_session_name,
    primary_from_user_messages,
)
from core.token_stats import apply_session_token_stats


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


def _cursor_user_data_root() -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library/Application Support/Cursor/User"
    if sys.platform == "win32":
        return home / "AppData/Roaming/Cursor/User"
    xdg = os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))
    return Path(xdg) / "Cursor/User"


def _file_uri_to_path(uri: str) -> str | None:
    u = uri.strip()
    if not u.startswith("file://"):
        return u if u else None
    parsed = urlparse(u)
    path = unquote(parsed.path or "")
    if sys.platform == "win32" and len(path) >= 3 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return path or None


def _project_path_from_meta_payload(payload: dict[str, object]) -> str | None:
    for key in (
        "workspacePath",
        "workspaceFolder",
        "workspaceUri",
        "folder",
        "rootPath",
        "projectPath",
        "cwd",
    ):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            s = val.strip()
            if s.startswith("file://"):
                return _file_uri_to_path(s)
            return s
    return None


def _decode_cursor_projects_slug(path: Path) -> str | None:
    try:
        parts = path.parts
        if ".cursor" not in parts or "projects" not in parts:
            return None
        idx = parts.index("projects")
        if idx + 1 >= len(parts):
            return None
        project_token = parts[idx + 1]
        if not project_token:
            return None

        decoded = project_token.strip("-")
        if not decoded:
            return None

        decoded = decoded.replace("--", "/")
        return f"/{decoded.replace('-', '/')}"
    except Exception:
        return None


def _project_path_from_workspace_json(store_db: Path) -> str | None:
    try:
        parts = store_db.resolve().parts
        idx = parts.index("chats")
    except ValueError:
        return None
    if idx + 1 >= len(parts):
        return None
    workspace_hash = parts[idx + 1]
    if not workspace_hash:
        return None

    wj = _cursor_user_data_root() / "workspaceStorage" / workspace_hash / "workspace.json"
    try:
        data = json.loads(wj.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    folder = data.get("folder")
    if isinstance(folder, str) and folder.strip():
        return _file_uri_to_path(folder.strip()) or folder.strip()
    return None


def _transcript_message_text(row: dict[str, object]) -> str | None:
    for key in ("content", "text", "message", "body"):
        val = row.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _normalize_transcript_role(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    r = raw.lower().strip()
    if r in {"human", "user"}:
        return MessageRole.USER.value
    if r in {"ai", "assistant", "agent"}:
        return MessageRole.ASSISTANT.value
    if r in {m.value for m in MessageRole}:
        return r
    return None


def _parse_transcript_jsonl(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        role = _normalize_transcript_role(row.get("role") or row.get("type"))
        if not role:
            continue
        msg = _transcript_message_text(row)
        if msg:
            out.append((role, msg))
    return out


def _parse_transcript_json_root(data: object) -> list[tuple[str, str]]:
    rows: list[object]
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        inner = None
        for key in ("messages", "history", "conversation", "turns"):
            v = data.get(key)
            if isinstance(v, list):
                inner = v
                break
        rows = inner if inner is not None else []
    else:
        return []

    out: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        role = _normalize_transcript_role(row.get("role") or row.get("type"))
        if not role:
            continue
        msg = _transcript_message_text(row)
        if msg:
            out.append((role, msg))
    return out


class CursorCrawler(BaseCrawler):
    def discover(self) -> list[str]:
        home = Path.home()
        paths: set[str] = set()
        chats = home / ".cursor" / "chats"
        if chats.exists():
            paths.update(str(p) for p in chats.glob("**/store.db"))
        projects = home / ".cursor" / "projects"
        if projects.exists():
            for at_dir in projects.glob("**/agent-transcripts"):
                if not at_dir.is_dir():
                    continue
                for pattern in ("*.jsonl", "*.json", "*.md", "*.txt"):
                    paths.update(str(p) for p in at_dir.glob(pattern))
        return sorted(paths)

    def parse(self, path: str) -> Session | None:
        source_path = Path(path)
        if not source_path.exists() or source_path.is_dir():
            return None

        if "agent-transcripts" in source_path.parts and source_path.suffix.lower() in {
            ".json",
            ".jsonl",
            ".md",
            ".txt",
        }:
            return self._parse_agent_transcript_file(source_path)

        conn = sqlite3.connect(source_path.as_posix())
        try:
            rows = conn.execute("SELECT key, value FROM meta").fetchall()
            merged_meta: dict[str, object] = {}
            last_decode_error: str | None = None
            for _key, value in rows:
                try:
                    decoded = _decode_hex_json(value)
                except Exception as exc:  # noqa: BLE001
                    last_decode_error = str(exc)
                    continue
                if isinstance(decoded, dict):
                    merged_meta.update({str(k): v for k, v in decoded.items()})

            if not merged_meta:
                detail = last_decode_error or "empty meta table"
                print(f"[warn] cannot decode cursor meta {path}: {detail}")
                return None

            project_path = _project_path_from_meta_payload(merged_meta)
            if not project_path:
                project_path = _project_path_from_workspace_json(source_path)

            session_id = str(merged_meta.get("agentId") or "")
            if not session_id:
                return None

            created_at = _parse_time(merged_meta.get("createdAt")) or datetime.fromtimestamp(
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

            user_texts = [
                c for role, c, _ in parsed_messages if role == MessageRole.USER.value
            ]
            meta_name = str(merged_meta.get("name") or "").strip()
            if meta_name and not is_generic_session_name(meta_name):
                primary_title = meta_name
            else:
                primary_title = primary_from_user_messages(
                    user_texts, fallback=meta_name or "Cursor"
                )

            session_title = finalize_session_title(
                primary=primary_title,
                project_path=project_path,
                source_path=source_path,
                created_at=created_at,
            )

            session = Session(
                id=session_id,
                source=SourceTool.CURSOR,
                project_path=project_path,
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

            apply_session_token_stats(session, None)
            return session
        finally:
            conn.close()

    def _parse_agent_transcript_file(self, source_path: Path) -> Session | None:
        session_id = hashlib.sha256(str(source_path.resolve()).encode()).hexdigest()
        project_path = _decode_cursor_projects_slug(source_path)
        raw_text = source_path.read_text(encoding="utf-8", errors="replace")
        suffix = source_path.suffix.lower()

        parsed_messages: list[tuple[str, str]] = []
        if suffix == ".jsonl":
            parsed_messages = _parse_transcript_jsonl(raw_text)
        elif suffix == ".json":
            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                return None
            parsed_messages = _parse_transcript_json_root(data)
        elif suffix in {".md", ".txt"}:
            body = raw_text.strip()
            if body:
                parsed_messages = [(MessageRole.ASSISTANT.value, body)]

        file_mtime = datetime.fromtimestamp(source_path.stat().st_mtime, tz=UTC)
        created_at = file_mtime

        user_texts = [t for role, t in parsed_messages if role == MessageRole.USER.value]
        title_primary = primary_from_user_messages(user_texts, fallback=source_path.stem)
        title = finalize_session_title(
            primary=title_primary,
            project_path=project_path,
            source_path=source_path,
            created_at=created_at,
        )

        session = Session(
            id=session_id,
            source=SourceTool.CURSOR,
            project_path=project_path,
            title=title,
            created_at=created_at,
            updated_at=file_mtime,
            message_count=len(parsed_messages),
            raw_path=str(source_path),
            messages=[],
        )

        for index, (role, content) in enumerate(parsed_messages):
            session.messages.append(
                Message(
                    id=_message_id(session_id, index),
                    session_id=session.id,
                    role=MessageRole(role),
                    content=content,
                    timestamp=None,
                )
            )

        apply_session_token_stats(session, None)
        return session
