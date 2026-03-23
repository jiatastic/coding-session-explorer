"""Build argv + cwd to resume a session in the vendor CLI (Codex / Cursor / Claude Code)."""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from pydantic import BaseModel, Field

from core.models import Session, SourceTool


class SessionResumeCommand(BaseModel):
    """Executable spec for `exec` / Bun.spawn — no shell interpolation."""

    argv: list[str]
    cwd: str | None = None
    hint: str = Field(
        default="",
        description="UX note shown in TUI stderr before handing off the terminal.",
    )


def _env_bin(name: str, default: str) -> str:
    v = os.environ.get(name, "").strip()
    return v if v else default


def _strip_title_suffix(title: str) -> str:
    """Remove leading ' · …' style prefix sometimes used in display titles."""
    t = title.strip()
    if " · " in t:
        return t.split(" · ", 1)[-1].strip()
    return t


def build_resume_command(session: Session) -> SessionResumeCommand:
    """Return argv/cwd for the native tool. IDs match Codex UUID and Cursor agentId only."""
    src = session.source
    if src == SourceTool.CODEX:
        bin_ = _env_bin("SESS_RESUME_CODEX_BIN", "codex")
        argv = [bin_, "resume"]
        if session.project_path:
            argv.extend(["-C", session.project_path])
        argv.append(session.id)
        return SessionResumeCommand(
            argv=argv,
            cwd=None,
            hint="",
        )

    if src == SourceTool.CURSOR:
        bin_ = _env_bin("SESS_RESUME_CURSOR_BIN", "agent")
        argv = [bin_]
        if session.project_path:
            argv.extend(["--workspace", session.project_path])
        argv.extend(["--resume", session.id])
        return SessionResumeCommand(argv=argv, cwd=None, hint="")

    if src == SourceTool.CLAUDE:
        bin_ = _env_bin("SESS_RESUME_CLAUDE_BIN", "claude")
        # Indexed id is a hash of the transcript path, not Claude's session UUID.
        if session.project_path:
            return SessionResumeCommand(
                argv=[bin_, "-c"],
                cwd=session.project_path,
                hint=(
                    "Claude: continues the most recent session in this directory "
                    "(indexed id is not Claude's session UUID)."
                ),
            )
        stem = Path(session.raw_path).stem.strip()
        token = stem or _strip_title_suffix(session.title)[:120].strip()
        if not token:
            return SessionResumeCommand(
                argv=[bin_, "--resume"],
                cwd=None,
                hint=(
                    "Claude: no project path — opening resume picker. "
                    "Indexed id is not Claude's native session id."
                ),
            )
        return SessionResumeCommand(
            argv=[bin_, "--resume", token],
            cwd=None,
            hint="Claude: resuming by transcript stem/name; may not match if ambiguous.",
        )

    raise ValueError(f"unsupported source: {src!r}")


def format_resume_shell(session: Session) -> str:
    """Single-line shell command for copy-paste (quoted)."""
    spec = build_resume_command(session)
    parts = [shlex.quote(p) for p in spec.argv]
    cmd = " ".join(parts)
    if spec.cwd:
        return f"cd {shlex.quote(spec.cwd)} && {cmd}"
    return cmd
