from __future__ import annotations

import re
import subprocess
from pathlib import Path


def origin_https_url(project_path: str | None) -> str | None:
    """Return https://github.com/... for origin if project_path is a git checkout, else None."""
    if not project_path or not str(project_path).strip():
        return None
    root = Path(project_path).expanduser()
    try:
        if not root.is_dir():
            return None
    except OSError:
        return None

    try:
        result = subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None

    raw = (result.stdout or "").strip()
    if not raw:
        return None
    return _to_https_github_url(raw)


def _to_https_github_url(raw: str) -> str | None:
    s = raw.strip()
    if s.startswith("https://github.com/") or s.startswith("http://github.com/"):
        return _normalize_github_https(s.replace("http://", "https://", 1))
    if s.startswith("git@github.com:"):
        rest = s.removeprefix("git@github.com:").removesuffix(".git")
        return _normalize_github_https(f"https://github.com/{rest}")
    if s.startswith("ssh://git@github.com/"):
        rest = s.removeprefix("ssh://git@github.com/").removesuffix(".git")
        return _normalize_github_https(f"https://github.com/{rest}")
    # gh repo clone uses https:// or other hosts — only promote GitHub for linking
    m = re.match(
        r"^(?:https?://)?(?:www\.)?github\.com[/:](?P<path>[\w.-]+/[\w.-]+?)(?:\.git)?/?$",
        s,
        re.IGNORECASE,
    )
    if m:
        return _normalize_github_https(f"https://github.com/{m.group('path')}")
    return None


def _normalize_github_https(url: str) -> str:
    u = url.rstrip("/")
    if u.endswith(".git"):
        u = u[:-4]
    return u
