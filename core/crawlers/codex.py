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


class CodexCrawler(BaseCrawler):
    def discover(self) -> list[str]:
        base = Path.home() / ".codex" / "sessions"
        return [str(p) for p in base.glob("**/*.jsonl")]

    def parse(self, path: str) -> Session | None:
        source_path = Path(path)
        if not source_path.exists() or source_path.is_dir():
            return None

        lines = source_path.read_text(encoding="utf-8").splitlines()
        if not lines:
            return None

        try:
            session_meta = json.loads(lines[0])
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid session_meta json: {exc}") from exc

        if session_meta.get("type") != "session_meta":
            raise ValueError("first record is not session_meta")

        payload = session_meta.get("payload") or {}
        session_id = str(payload.get("id") or "")
        if not session_id:
            raise ValueError("session_meta missing payload.id")

        created_time = _parse_time(payload.get("timestamp"))
        project_path = payload.get("cwd")
        if not isinstance(project_path, str) or not project_path:
            project_path = None

        parsed_messages: list[tuple[str, str, datetime | None]] = []
        for line in lines[1:]:
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg_type = raw.get("type")
            if not isinstance(msg_type, str) or msg_type not in {m.value for m in MessageRole}:
                continue
            content = str(raw.get("content") or "").strip()
            if not content:
                continue
            parsed_messages.append((str(msg_type), content, _parse_time(raw.get("timestamp"))))

        if not parsed_messages:
            return None

        file_mtime = datetime.fromtimestamp(source_path.stat().st_mtime, tz=UTC)
        if created_time is None:
            created_time = file_mtime

        first_user = next(
            (content for role, content, _ in parsed_messages if role == MessageRole.USER.value),
            None,
        )
        title = (first_user[:80] if first_user else source_path.stem) or source_path.stem

        session = Session(
            id=session_id,
            source=SourceTool.CODEX,
            project_path=project_path,
            title=title,
            created_at=created_time,
            updated_at=max(created_time, file_mtime),
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

        return session
