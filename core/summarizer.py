from __future__ import annotations

import logging

from core import db
from core.config import get_summarization_settings
from core.models import Session
from core.secrets import get_openai_api_key

log = logging.getLogger("sess.summarize")

MAX_TRANSCRIPT_CHARS = 14_000
MAX_MESSAGE_CHARS = 4_000

SYSTEM_PROMPT = (
    "You summarize coding assistant conversations. In 1–3 short English sentences, "
    "cover the topic, what was done, and the outcome or conclusion. "
    "Do not quote or restate code blocks; no bullet lists. Stay under about 120 words."
)


def _build_transcript(session: Session) -> str:
    parts: list[str] = []
    for message in session.messages:
        role = message.role.value
        body = (message.content or "").strip().replace("\r\n", "\n")
        if len(body) > MAX_MESSAGE_CHARS:
            body = body[: MAX_MESSAGE_CHARS - 1] + "…"
        if body:
            parts.append(f"{role}: {body}")
    text = "\n\n".join(parts)
    if len(text) > MAX_TRANSCRIPT_CHARS:
        return text[: MAX_TRANSCRIPT_CHARS - 1] + "…"
    return text


def summarize_session_text(session: Session) -> str | None:
    """Call OpenAI Chat Completions; returns None on skip or failure."""
    settings = get_summarization_settings()
    if not settings["enabled"]:
        return None
    api_key = (get_openai_api_key() or "").strip()
    if not api_key:
        return None
    transcript = _build_transcript(session)
    if not transcript.strip():
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=str(settings["model"]),
            temperature=0.2,
            max_tokens=400,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": transcript},
            ],
        )
    except Exception:
        log.exception("OpenAI summarization failed for session %s", session.id)
        return None

    choice = response.choices[0].message.content
    if not choice:
        return None
    summary = choice.strip()
    return summary or None


def maybe_summarize_session(session_id: str) -> bool:
    """If configured and API key present, write summary for sessions that lack one."""
    session = db.get_session(session_id)
    if session is None or session.summary:
        return False
    if not session.messages:
        return False

    text = summarize_session_text(session)
    if not text:
        return False

    db.update_session_summary(session_id, text)
    return True


def summarize_missing_sessions(
    limit: int = 500,
    *,
    recent_days: int | None = None,
) -> int:
    """Backfill summaries for rows with NULL summary and message_count > 0."""
    ids = db.list_session_ids_missing_summary(limit=limit, recent_days=recent_days)
    done = 0
    for sid in ids:
        if maybe_summarize_session(sid):
            done += 1
    return done
