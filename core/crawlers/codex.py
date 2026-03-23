from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from core.crawlers.base import BaseCrawler
from core.models import Message, MessageRole, Session, SourceTool
from core.title_utils import finalize_session_title, primary_from_user_messages
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


def _flatten_response_content(content: object) -> str:
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        t = item.get("type")
        if t in ("input_text", "output_text"):
            tx = item.get("text")
            if isinstance(tx, str) and tx.strip():
                parts.append(tx.strip())
        elif t == "input_image":
            url = item.get("image_url")
            if isinstance(url, str) and url.strip():
                parts.append(f"[image: {url.strip()}]")
    return "\n".join(parts)


def _extract_messages_from_rollout_line(
    raw: dict[str, object],
) -> list[tuple[str, str, datetime | None]]:
    ts = _parse_time(raw.get("timestamp"))
    top_type = raw.get("type")
    if not isinstance(top_type, str):
        return []

    if top_type in {m.value for m in MessageRole}:
        content = str(raw.get("content") or "").strip()
        if content:
            return [(top_type, content, ts)]
        return []

    payload = raw.get("payload")
    if not isinstance(payload, dict):
        payload = {}

    if top_type == "event_msg":
        inner = payload.get("type")
        if inner == "user_message":
            msg = str(payload.get("message") or "").strip()
            if msg:
                return [(MessageRole.USER.value, msg, None)]
        elif inner == "agent_message":
            msg = str(payload.get("message") or "").strip()
            if msg:
                return [(MessageRole.ASSISTANT.value, msg, None)]
        return []

    if top_type == "response_item":
        ptype = payload.get("type")
        if ptype == "message":
            role = str(payload.get("role") or "assistant").lower()
            if role not in {m.value for m in MessageRole}:
                role = MessageRole.ASSISTANT.value
            text = _flatten_response_content(payload.get("content")).strip()
            if text:
                return [(role, text, None)]
        if ptype == "function_call":
            name = str(payload.get("name") or "function_call").strip()
            args = str(payload.get("arguments") or "").strip()
            text = f"{name}({args})".strip() if args else name
            if text:
                return [(MessageRole.TOOL.value, text, None)]
        return []

    if top_type == "compacted":
        msg = str(payload.get("message") or "").strip()
        if msg:
            return [(MessageRole.ASSISTANT.value, msg, None)]
        return []

    return []


def _find_session_meta(lines: list[str]) -> tuple[dict[str, object] | None, int | None]:
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("type") != "session_meta":
            continue
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        return payload, i
    return None, None


def _codex_home_candidates() -> list[Path]:
    """Roots that mirror Codex's layout: <root>/sessions, <root>/archived_sessions.

    See openai/codex: ``codex_utils_home_dir::find_codex_home`` (``~/.codex`` or
    ``CODEX_HOME``) and ``codex-rs/core/src/rollout/mod.rs`` (``sessions``,
    ``archived_sessions`` subdirs).
    """
    roots: list[Path] = []
    roots.append(Path.home() / ".codex")
    codex_home = os.environ.get("CODEX_HOME", "").strip()
    if codex_home:
        roots.append(Path(codex_home).expanduser())
    cur = Path.cwd().resolve()
    for _ in range(128):
        roots.append(cur / ".codex")
        if cur.parent == cur:
            break
        cur = cur.parent
    return roots


def iter_codex_rollout_directories() -> list[Path]:
    """Existing rollout directories to scan (``**/*.jsonl``) and to watch."""
    seen: set[str] = set()
    out: list[Path] = []
    for root in _codex_home_candidates():
        try:
            resolved = root.expanduser().resolve()
        except (OSError, RuntimeError):
            continue
        if not resolved.is_dir():
            continue
        for name in ("sessions", "archived_sessions"):
            d = resolved / name
            if not d.is_dir():
                continue
            try:
                key = str(d.resolve())
            except OSError:
                key = str(d)
            if key in seen:
                continue
            seen.add(key)
            out.append(d)
    return out


class CodexCrawler(BaseCrawler):
    def discover(self) -> list[str]:
        paths: set[str] = set()
        for d in iter_codex_rollout_directories():
            paths.update(str(p) for p in d.glob("**/*.jsonl"))
        return sorted(paths)

    def parse(self, path: str) -> Session | None:
        source_path = Path(path)
        if not source_path.exists() or source_path.is_dir():
            return None

        lines = source_path.read_text(encoding="utf-8").splitlines()
        if not lines:
            return None

        payload, _meta_idx = _find_session_meta(lines)
        if payload is None:
            raise ValueError("no session_meta record found")

        session_id = str(payload.get("id") or "")
        if not session_id:
            raise ValueError("session_meta missing payload.id")

        created_time = _parse_time(payload.get("timestamp"))
        project_path = payload.get("cwd")
        if not isinstance(project_path, str) or not project_path:
            project_path = None

        parsed_messages: list[tuple[str, str, datetime | None]] = []
        last_turn_cwd: str | None = None

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue

            top_type = raw.get("type")
            if top_type == "turn_context":
                pl = raw.get("payload")
                if isinstance(pl, dict):
                    cwd = pl.get("cwd")
                    if isinstance(cwd, str) and cwd.strip():
                        last_turn_cwd = cwd.strip()

            for role, content, ts in _extract_messages_from_rollout_line(raw):
                parsed_messages.append((role, content, ts))

        if not project_path and last_turn_cwd:
            project_path = last_turn_cwd

        file_mtime = datetime.fromtimestamp(source_path.stat().st_mtime, tz=UTC)
        if created_time is None:
            created_time = file_mtime

        user_texts = [
            c for role, c, _ in parsed_messages if role == MessageRole.USER.value
        ]
        title_primary = primary_from_user_messages(user_texts, fallback=source_path.stem)
        title = finalize_session_title(
            primary=title_primary,
            project_path=project_path,
            source_path=source_path,
            created_at=created_time,
        )

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

        apply_session_token_stats(session, lines)
        return session
