"""Console entrypoint: ensure repo (or site-packages) is on sys.path before importing cli."""

from __future__ import annotations

import sys
from pathlib import Path


def _candidate_roots() -> list[str]:
    """Directories that may contain the ``cli`` package (editable broken, or running from a subfolder)."""
    seen: set[str] = set()
    out: list[str] = []
    launcher_dir = Path(__file__).resolve().parent
    cwd = Path.cwd().resolve()
    for base in (launcher_dir, cwd, *cwd.parents):
        if (base / "cli" / "main.py").is_file():
            s = str(base)
            if s not in seen:
                seen.add(s)
                out.append(s)
    return out


def main() -> int:
    try:
        from cli.main import app as typer_app
    except ModuleNotFoundError:
        for root in _candidate_roots():
            if root not in sys.path:
                sys.path.insert(0, root)
            try:
                from cli.main import app as typer_app  # noqa: PLC0415
                break
            except ModuleNotFoundError:
                continue
        else:
            raise ModuleNotFoundError(
                "Could not import cli.main. Try: uv sync && uv pip install -e ."
            ) from None

    code = typer_app()
    return int(code) if code is not None else 0
