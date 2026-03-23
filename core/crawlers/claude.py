from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from core.crawlers.base import BaseCrawler
from core.models import Message, MessageRole, Session, SourceTool


def _message_id(session_id: str, index: int) -> str:
    return hashlib.sha256(f"{session_id}:{index}".encode()).hexdigest()


def _parse_time(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _decode_project_path(path: Path) -> str | None:
    try:
        parts = path.parts
        if ".claude" not in parts or "projects" not in parts:
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


class ClaudeCrawler(BaseCrawler):
    def discover(self) -> list[str]:
        home = Path.home()
        base = home / ".claude"
        return [str(p) for p in (base / "transcripts").glob("*.jsonl")] + [
            str(p) for p in (base / "projects").glob("**/*.jsonl")
        ]

    def parse(self, path: str) -> Session | None:
        source_path = Path(path)
        if not source_path.exists() or source_path.is_dir():
            return None

        lines = source_path.read_text(encoding="utf-8").splitlines()
        parsed: list[dict[str, object]] = []
        for line in lines:
            try:
                parsed.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        title = source_path.stem
        summary: str | None = None
        parsed_messages: list[tuple[str, str, datetime | None]] = []

        for raw in parsed:
            msg_type = raw.get("type")
            if msg_type == "summary":
                summary = str(raw.get("summary") or "").strip()
                if summary:
                    title = summary
            elif msg_type in {MessageRole.USER.value, MessageRole.ASSISTANT.value}:
                message_type = str(msg_type)
                content = str(raw.get("content") or "").strip()
                if not content:
                    continue
                parsed_messages.append((message_type, content, _parse_time(raw.get("timestamp"))))

        if not parsed_messages:
            return None

        session_id = _message_id(str(source_path), 0)
        session = Session(
            id=session_id,
            source=SourceTool.CLAUDE,
            project_path=_decode_project_path(source_path),
            title=title,
            created_at=parsed_messages[0][2]
            or datetime.fromtimestamp(source_path.stat().st_mtime, tz=UTC),
            updated_at=datetime.fromtimestamp(source_path.stat().st_mtime, tz=UTC),
            message_count=len(parsed_messages),
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

        if summary:
            session.title = summary

        return session
