"""Optional OpenAI-generated session titles (heuristic title is always the fallback)."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from core import db
from core.config import get_summarization_settings
from core.secrets import get_openai_api_key
from core.title_utils import with_project_prefix

if TYPE_CHECKING:
    from core.models import Session

log = logging.getLogger("sess.title_ai")

_TITLE_SYSTEM = (
    "You write a single line title for a coding-assistant chat shown in a local session browser. "
    "Rules: under 14 words; no quotes or emoji; no markdown; end without . ! ? when possible. "
    "Match the user's language if the conversation is clearly non-English; otherwise English. "
    "Describe the task, area, or outcome (e.g. 'OAuth redirect fix in Next.js'). "
    "Reply with only the title line, nothing else."
)

_MAX_EXCERPT = 12_000
_MAX_MSG = 2_000


def _excerpt_for_title(session: Session) -> str:
    parts: list[str] = []
    for message in session.messages[:12]:
        role = message.role.value
        body = (message.content or "").strip().replace("\r\n", "\n")
        if len(body) > _MAX_MSG:
            body = body[: _MAX_MSG - 1] + "…"
        if body:
            parts.append(f"{role}: {body}")
    text = "\n\n".join(parts)
    if len(text) > _MAX_EXCERPT:
        return text[: _MAX_EXCERPT - 1] + "…"
    return text


def _clean_model_title(raw: str) -> str | None:
    line = (raw or "").strip().splitlines()[0].strip()
    line = line.strip("\"'「」『』")
    line = re.sub(r"^[\s#*\-]+", "", line).strip()
    if len(line) < 3:
        return None
    if len(line) > 160:
        line = line[:157] + "…"
    return line


def suggest_ai_title(session: Session) -> str | None:
    """Call OpenAI Chat Completions; returns None on skip or failure."""
    settings = get_summarization_settings()
    if not settings.get("title_ai"):
        return None
    api_key = (get_openai_api_key() or "").strip()
    if not api_key:
        return None
    excerpt = _excerpt_for_title(session)
    if not excerpt.strip():
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=str(settings["model"]),
            temperature=0.3,
            max_tokens=80,
            messages=[
                {"role": "system", "content": _TITLE_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"Current heuristic title (hint only): {session.title!r}\n\n---\n{excerpt}"
                    ),
                },
            ],
        )
    except Exception:
        log.exception("OpenAI title generation failed for session %s", session.id)
        return None

    choice = response.choices[0].message.content
    return _clean_model_title(choice or "")


def maybe_ai_session_title(session_id: str) -> bool:
    """Replace DB title with AI suggestion (+ project prefix) when enabled and API key is set."""
    session = db.get_session(session_id)
    if session is None or not session.messages:
        return False

    suggested = suggest_ai_title(session)
    if not suggested:
        return False

    final = with_project_prefix(suggested, session.project_path)
    db.update_session_title(session_id, final)
    return True
