"""Derive readable session titles from repetitive first-turn boilerplate."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

_AGENTS_INSTRUCTIONS = re.compile(
    r"^\s*#\s*AGENTS\.md\s+instructions\s+for\s+",
    re.IGNORECASE | re.DOTALL,
)

_GENERIC_CHAT_NAMES = re.compile(
    r"^\s*(cursor session|new chat|chat|untitled|conversation)\s*(\d+)?\s*$",
    re.IGNORECASE,
)

_LOW_SIGNAL_USER = re.compile(
    r"^\s*(hi|hey|hello|there|ok+|k|thanks|thx+|ty+|continue|go on|yep|yeah|yes|no|nope|"
    r"pls|please|done|got it|sounds good|sure|np|lgtm|same|this|that)\s*[!?.…]*\s*$",
    re.IGNORECASE,
)

_OPAQUE_STEM = re.compile(r"^[0-9a-f]{20,}$|^[0-9a-f-]{32,}$", re.IGNORECASE)


def is_agents_md_instruction_opening(text: str) -> bool:
    return bool(_AGENTS_INSTRUCTIONS.match(text.strip()))


def is_generic_session_name(text: str) -> bool:
    """True for empty / default UI labels that are not useful as a title."""
    s = (text or "").strip()
    if len(s) < 2:
        return True
    return bool(_GENERIC_CHAT_NAMES.match(s))


def looks_like_opaque_stem(stem: str) -> bool:
    """Heuristic: filename stem that is probably not human-readable."""
    s = stem.strip()
    if len(s) >= 36 and s.count("-") >= 4:
        return True
    return bool(_OPAQUE_STEM.match(s))


def _truncate_smart(s: str, max_len: int) -> str:
    s = s.strip()
    if len(s) <= max_len:
        return s
    cut = s[: max_len - 1].rsplit(" ", 1)[0]
    if len(cut) < max_len // 3:
        cut = s[: max_len - 1]
    return f"{cut}…"


def _is_low_signal_user_message(text: str) -> bool:
    s = text.strip()
    if len(s) < 2:
        return True
    if _LOW_SIGNAL_USER.match(s):
        return True
    if s in {"```", "```python", "```typescript", "```ts", "```js"}:
        return True
    return False


def _first_substantive_line(text: str, max_len: int) -> str:
    for line in text.splitlines():
        ln = line.strip()
        if not ln:
            continue
        ln = re.sub(r"^#+\s*", "", ln).strip()
        if len(ln) < 3:
            continue
        return _truncate_smart(ln, max_len)
    return _truncate_smart(text.strip(), max_len)


def project_basename(project_path: str | None) -> str | None:
    if not project_path:
        return None
    try:
        name = Path(project_path.rstrip("/")).name
        return name if name else None
    except (OSError, ValueError):
        return None


def primary_from_user_messages(user_messages: list[str], *, fallback: str) -> str:
    """Pick the first substantive user turn; keep AGENTS.md lines for refined_session_title."""
    for raw in user_messages:
        u = raw.strip()
        if not u:
            continue
        if is_agents_md_instruction_opening(u):
            return u[:4000]
        if _is_low_signal_user_message(u):
            continue
        line = _first_substantive_line(u, max_len=96)
        if line and not _is_low_signal_user_message(line):
            return line
    fb = fallback.strip()
    if fb and not looks_like_opaque_stem(fb):
        return _truncate_smart(fb, 96)
    return fb or "Session"


def with_project_prefix(title: str, project_path: str | None, *, max_len: int = 100) -> str:
    """Prefix with repo folder name when the title does not already imply it."""
    proj = project_basename(project_path)
    if not proj:
        return _truncate_smart(title, max_len)
    t = title.strip()
    if not t:
        return proj
    if proj.lower() in t.lower():
        return _truncate_smart(t, max_len)
    merged = f"{proj} · {t}"
    return _truncate_smart(merged, max_len)


def refined_session_title(
    *,
    primary: str,
    project_path: str | None,
    source_path: Path,
    created_at: datetime | None,
) -> str:
    """Replace long AGENTS.md path boilerplate with repo slug + timestamp."""
    p = (primary or "").strip()
    if not p:
        return source_path.stem or "Session"

    m = _AGENTS_INSTRUCTIONS.match(p)
    if not m:
        return p

    rest = p[m.end() :].strip()
    slug = ""
    if rest:
        tail = rest.splitlines()[0].strip()
        slug = Path(tail.rstrip("/")).name or tail[-48:].strip()
    if not slug and project_path:
        slug = Path(project_path.rstrip("/")).name
    if not slug:
        slug = source_path.stem[:32] or "project"

    ts: datetime | None = created_at
    if ts is None and source_path.exists():
        ts = datetime.fromtimestamp(source_path.stat().st_mtime, tz=UTC)
    time_part = ts.astimezone(UTC).strftime("%Y-%m-%d %H:%M") if ts else ""

    base = f"AGENTS · {slug}"
    return f"{base} · {time_part}" if time_part else base


def finalize_session_title(
    *,
    primary: str,
    project_path: str | None,
    source_path: Path,
    created_at: datetime | None,
) -> str:
    """Run AGENTS.md refinement, then add a readable repo prefix when helpful."""
    refined = refined_session_title(
        primary=primary,
        project_path=project_path,
        source_path=source_path,
        created_at=created_at,
    )
    return with_project_prefix(refined, project_path)
