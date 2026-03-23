from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from core.crawlers.base import BaseCrawler
from core.crawlers.claude_text import (
    pick_dominant_cwd,
    text_from_claude_assistant_line,
    text_from_claude_user_line,
)
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

        summary: str | None = None
        parsed_messages: list[tuple[str, str, datetime | None]] = []
        user_texts: list[str] = []

        for raw in parsed:
            msg_type = raw.get("type")
            if msg_type == "summary":
                summary = str(raw.get("summary") or "").strip() or None
            elif msg_type == MessageRole.USER.value:
                content = text_from_claude_user_line(raw)
                if not content:
                    continue
                user_texts.append(content)
                parsed_messages.append(
                    (MessageRole.USER.value, content, _parse_time(raw.get("timestamp")))
                )
            elif msg_type == MessageRole.ASSISTANT.value:
                content = text_from_claude_assistant_line(raw)
                if not content:
                    continue
                parsed_messages.append(
                    (MessageRole.ASSISTANT.value, content, _parse_time(raw.get("timestamp")))
                )

        if not parsed_messages:
            return None

        project_path = _decode_project_path(source_path) or pick_dominant_cwd(parsed)

        created_at = parsed_messages[0][2] or datetime.fromtimestamp(
            source_path.stat().st_mtime, tz=UTC
        )
        summary_stripped = (summary or "").strip()
        if (
            summary_stripped
            and len(summary_stripped) > 8
            and not is_generic_session_name(summary_stripped)
        ):
            title_candidate = summary_stripped
        elif user_texts:
            title_candidate = primary_from_user_messages(user_texts, fallback=source_path.stem)
        else:
            title_candidate = source_path.stem

        final_title = finalize_session_title(
            primary=title_candidate,
            project_path=project_path,
            source_path=source_path,
            created_at=created_at,
        )

        session_id = _message_id(str(source_path), 0)
        session = Session(
            id=session_id,
            source=SourceTool.CLAUDE,
            project_path=project_path,
            title=final_title,
            created_at=created_at,
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

        apply_session_token_stats(session, None)
        return session
