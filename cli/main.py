from __future__ import annotations

import builtins
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import cast

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[misc, assignment]

import typer
import uvicorn
from rich.console import Console
from rich.live import Live
from rich.logging import RichHandler
from rich.text import Text

from cli import display
from core import db, index_progress
from core import search as search_module
from core.config import get_embedding_settings, get_server_settings, load_config
from core.crawlers import ClaudeCrawler, CodexCrawler, CursorCrawler
from core.crawlers.codex import iter_codex_rollout_directories
from core.embedder import set_provider
from core.git_remote import origin_https_url
from core.indexer import index_all
from core.models import SourceTool
from core.summarizer import summarize_missing_sessions
from core.watcher import create_observer


def _bootstrap_env() -> None:
    if load_dotenv is None:
        return
    repo_root = Path(__file__).resolve().parents[1]
    load_dotenv(repo_root / ".env")
    load_dotenv()


_bootstrap_env()

app = typer.Typer(
    help=(
        "Session explorer — bare `sess` opens the TUI when Bun + OpenTUI are installed; "
        "otherwise prints the session list (same as `sess list`)."
    ),
    invoke_without_command=True,
)
console = Console()
log = logging.getLogger("sess")


@app.callback()
def _default_command(
    ctx: typer.Context,
    port: int | None = typer.Option(
        None,
        "--port",
        help="API port when running bare `sess` (TUI); defaults to [server].port in config.",
    ),
    strict_port: bool = typer.Option(
        False,
        "--strict-port",
        help="Fail if --port is busy instead of trying the next free port "
        "(also set [server].strict_port or SESS_TUI_STRICT_PORT).",
        is_flag=True,
    ),
) -> None:
    if ctx.invoked_subcommand is None:
        settings = get_server_settings()
        api_port = port if port is not None else settings["port"]
        strict = strict_port or settings["strict_port"]
        if _tui_ready():
            _run_tui(port=api_port, no_serve=False, strict_port=strict)
        else:
            _run_default_without_tui()


def _resolve_tool(tool: str | None) -> SourceTool | None:
    if tool is None:
        return None
    try:
        return SourceTool(tool)
    except ValueError as exc:
        raise typer.BadParameter("tool must be claude|codex|cursor") from exc


def _find_session_by_prefix(value: str) -> str | None:
    sessions = db.list_sessions(limit=5000)
    exact = [session.id for session in sessions if session.id == value]
    if exact:
        return exact[0]
    matches = [session.id for session in sessions if session.id.startswith(value)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise typer.BadParameter(f"session id prefix is ambiguous: {', '.join(matches[:3])}")
    return None


def _run_index(
    *,
    force: bool,
    summarize_missing: bool,
    recent_days: int | None,
) -> None:
    embedding_settings = get_embedding_settings()
    set_provider(embedding_settings)

    db.init_db()

    index_progress.reset_running()
    result: dict[str, object] = {}
    thread_error: builtins.list[BaseException] = []

    def _index_worker() -> None:
        try:
            result["aggregate"] = index_all(
                force=force, report_progress=True, recent_days=recent_days
            )
        except BaseException as exc:
            thread_error.append(exc)

    th = threading.Thread(target=_index_worker, name="sess-index-all")
    th.start()
    try:
        with Live(
            Text("Starting index…", style="cyan"),
            console=console,
            refresh_per_second=12,
        ) as live:
            while th.is_alive():
                snap = index_progress.snapshot()
                crawler = snap["crawler"] or "—"
                cur, tot = snap["current"], snap["total"]
                detail = snap["detail"]
                if tot:
                    header = f"[bold]{crawler}[/bold]  {cur}/{tot}"
                else:
                    header = f"[bold]{crawler}[/bold]"
                if detail:
                    live.update(Text.from_markup(f"{header}\n[dim]{detail}[/dim]"))
                else:
                    live.update(Text.from_markup(header))
                th.join(timeout=0.06)
            th.join()
        if thread_error:
            raise thread_error[0]
        raw_agg = result.get("aggregate")
        if not isinstance(raw_agg, dict):
            raise RuntimeError("index finished without aggregate stats")
        aggregate = cast(dict[str, int], raw_agg)
        index_progress.finish(aggregate)
    except Exception as exc:
        index_progress.fail(str(exc))
        raise

    aggregate = cast(dict[str, int], result["aggregate"])

    console.print(
        display.render_summary(
            aggregate["new_sessions"],
            aggregate["new_messages"],
            aggregate["skipped"],
            skipped_heavy=int(aggregate.get("skipped_heavy", 0)),
        )
    )

    if summarize_missing:
        filled = summarize_missing_sessions(limit=500, recent_days=recent_days)
        console.print(f"[cyan]Summaries written:[/cyan] {filled} session(s)")


@app.command()
def index(
    force: bool = typer.Option(
        False,
        "--force",
        help="Reindex even unchanged sessions (shortcut: sess reindex)",
    ),
    summarize_missing: bool = typer.Option(
        False,
        "--summarize-missing",
        help="After indexing, backfill AI summaries where missing (requires OPENAI_API_KEY)",
    ),
    recent_days: int | None = typer.Option(
        None,
        "--recent-days",
        min=1,
        help="Only embed + AI (summary/title) for sessions updated in the last N days; "
        "DB rows are still updated for all sources.",
    ),
) -> None:
    _run_index(force=force, summarize_missing=summarize_missing, recent_days=recent_days)


@app.command()
def reindex(
    summarize_missing: bool = typer.Option(
        False,
        "--summarize-missing",
        help="After reindexing, backfill AI summaries where missing (requires OPENAI_API_KEY)",
    ),
    recent_days: int | None = typer.Option(
        None,
        "--recent-days",
        min=1,
        help="Only embed + AI for sessions updated in the last N days (see `sess index --help`).",
    ),
) -> None:
    """Reindex all sources with --force (same as `sess index --force`)."""
    _run_index(force=True, summarize_missing=summarize_missing, recent_days=recent_days)


@app.command()
def reset(
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation (required for scripts).",
    ),
    all_data: bool = typer.Option(
        False,
        "--all",
        help="Delete the entire ~/.coding-sessions directory (config.toml, secrets.json, everything).",
    ),
    reindex_after: bool = typer.Option(
        False,
        "--reindex",
        help="Run a full index immediately after reset.",
    ),
) -> None:
    """Remove local SQLite index and Chroma vectors; optional full data wipe and reindex."""
    root = db.get_data_root()
    if not yes:
        if all_data:
            ok = typer.confirm(
                f"Delete ALL app data under {root} (including config and saved API keys)?",
                default=False,
            )
        else:
            ok = typer.confirm(
                "Remove sessions.db and chroma/ only (keep config.toml and secrets.json)?",
                default=False,
            )
        if not ok:
            raise typer.Abort()

    db.invalidate_engine()
    removed = db.reset_index_storage(remove_entire_data_dir=all_data)
    if removed:
        for line in removed:
            console.print(f"[dim]removed[/dim] {line}")
    else:
        console.print("[yellow]Nothing to remove (paths were already absent).[/yellow]")

    if reindex_after:
        console.print("[cyan]Reindexing…[/cyan]")
        _run_index(force=True, summarize_missing=False, recent_days=None)
    else:
        console.print("[dim]Run[/dim] [bold]sess index[/bold] [dim]when you want a fresh index.[/dim]")


@app.command()
def list(
    tool: str | None = typer.Option(None, "--tool", help="Filter by claude|codex|cursor"),
    project: str | None = typer.Option(None, "--project", help="Filter by project path"),
    days: int | None = typer.Option(None, "--days", help="Only sessions updated within N days"),
    limit: int = typer.Option(100, "--limit", help="Max sessions to show"),
) -> None:
    selected = _resolve_tool(tool)
    sessions = db.list_sessions(tool=selected, project=project, days=days, limit=limit)
    if not sessions:
        console.print("[yellow]No sessions found[/yellow]")
        return
    console.print(display.render_session_table(sessions))


@app.command()
def view(session_id: str) -> None:
    resolved = _find_session_by_prefix(session_id)
    if not resolved:
        raise typer.BadParameter("session not found")

    session = db.get_session(resolved)
    if session is None:
        raise typer.BadParameter("session not found")

    display.render_message_view(session)


@app.command()
def search(
    query: str,
    limit: int = typer.Option(10, "--limit", help="Max results to return"),
    mode: str = typer.Option("auto", "--mode", help="semantic | fulltext"),
) -> None:
    if not query.strip():
        raise typer.BadParameter("query cannot be empty")
    if mode not in {"semantic", "fulltext", "auto"}:
        raise typer.BadParameter("mode must be semantic, fulltext, or auto")

    results = search_module.search(query=query.strip(), n_results=limit, mode=mode)
    if not results:
        console.print("[yellow]No results found[/yellow]")
        return

    console.print(display.render_search_table(results))


@app.command()
def stats(year: int | None = typer.Option(None, "--year", help="Optional year filter")) -> None:
    console.print(display.render_stats(year=year))


def _index_file(path: Path) -> None:
    target = path.as_posix()
    parsed = None
    source_settings = load_config().get("sources", {})
    if not source_settings.get("claude", True) and "/.claude/" in target:
        return
    if not source_settings.get("codex", True) and "/.codex/" in target:
        return
    if not source_settings.get("cursor", True) and "/.cursor/" in target:
        return

    try:
        if "/.claude/" in target:
            parsed = ClaudeCrawler().parse(target)
        elif "/.codex/" in target:
            parsed = CodexCrawler().parse(target)
        elif "/.cursor/" in target:
            parsed = CursorCrawler().parse(target)
    except Exception:
        log.exception("failed to parse changed file %s", target)
        return

    if parsed is None:
        return

    parsed.repo_url = origin_https_url(parsed.project_path)
    db.init_db()
    upserted = db.upsert_session(parsed)
    if upserted:
        from core.embedder import embed_session
        from core.summarizer import maybe_summarize_session

        embed_session(parsed)
        maybe_summarize_session(parsed.id)
    log.info("indexed %s (%s)", target, "updated" if upserted else "unchanged")


@app.command()
def watch() -> None:
    logging.basicConfig(
        level=logging.INFO, handlers=[RichHandler(rich_tracebacks=True)], format="%(message)s"
    )
    db.init_db()

    home = Path.home()
    paths = [str(home / ".claude" / "transcripts")]
    paths.extend(str(d) for d in iter_codex_rollout_directories())
    paths.extend(
        [
            str(home / ".cursor" / "chats"),
            str(home / ".cursor" / "projects"),
        ]
    )
    paths = [path for path in paths if Path(path).exists()]

    if not paths:
        raise typer.BadParameter("no source directories found for watch")

    console.print("[blue]Watching source directories. Press Ctrl+C to stop.[/blue]")
    observer = create_observer(paths, lambda event_path: _index_file(Path(event_path)))
    observer.start()

    try:
        with Live("[dim]Watching...[/dim]", console=console, refresh_per_second=1):
            while True:
                import time

                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        console.print("[yellow]watch stopped[/yellow]")


@app.command()
def serve(port: int = typer.Option(8000, "--port", help="Port to serve FastAPI on")) -> None:
    uvicorn.run("server.main:app", host="127.0.0.1", port=port, reload=False)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _health_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=0.35) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _can_bind_tcp(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _first_free_port(host: str, start: int, *, span: int = 32) -> int | None:
    for p in range(start, start + span):
        if _can_bind_tcp(host, p):
            return p
    return None


def _tui_ready() -> bool:
    root = _repo_root()
    opentui = root / "tui" / "node_modules" / "@opentui" / "core"
    return opentui.is_dir() and shutil.which("bun") is not None


def _run_default_without_tui() -> None:
    db.init_db()
    sessions = db.list_sessions(limit=100)
    if not sessions:
        console.print("[yellow]No sessions found.[/yellow]")
        console.print("[dim]Run[/dim] [bold]sess index[/bold] [dim]to import history.[/dim]")
    else:
        console.print(display.render_session_table(sessions))
    console.print(
        "[dim]OpenTUI browser:[/dim] [bold]cd tui && bun install[/bold] [dim]then[/dim] [bold]sess tui[/bold][dim]. "
        "More:[/dim] [bold]sess --help[/bold][dim].[/dim]"
    )


def _run_tui(*, port: int, no_serve: bool, strict_port: bool = False) -> None:
    """Start optional API + OpenTUI. Exits the process via typer.Exit."""
    root = _repo_root()
    tui_dir = root / "tui"
    opentui = tui_dir / "node_modules" / "@opentui" / "core"
    if not opentui.is_dir():
        console.print("[red]Missing OpenTUI — run:[/red] cd tui [dim]&&[/dim] bun install")
        raise typer.Exit(1)
    if shutil.which("bun") is None:
        console.print("[red]Bun is required for the TUI.[/red] See https://bun.sh/")
        raise typer.Exit(1)

    host = "127.0.0.1"
    serve_proc: subprocess.Popen[bytes] | None = None
    api_port = port

    if not no_serve:
        health_existing = f"http://{host}:{port}/health"
        if _health_ok(health_existing):
            api_port = port
        else:
            if strict_port:
                if not _can_bind_tcp(host, port):
                    console.print(
                        f"[red]Port {port} is not available "
                        f"([bold]--strict-port[/bold] / [server].strict_port). "
                        f"Free it or use a different [bold]--port[/bold].[/red]"
                    )
                    raise typer.Exit(1)
                picked = port
            else:
                picked = _first_free_port(host, port)
                if picked is None:
                    console.print(
                        f"[red]Could not bind the API on {host}:{port}–{port + 31} "
                        "(all busy). Free a port or use [bold]--port[/bold].[/red]"
                    )
                    raise typer.Exit(1)
            api_port = picked
            if not strict_port and api_port != port:
                console.print(
                    f"[yellow]Port {port} is not available; "
                    f"starting API on {api_port} instead.[/yellow]"
                )
            env = os.environ.copy()
            pp = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = f"{root}{os.pathsep}{pp}" if pp else str(root)
            try:
                serve_proc = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "server.main:app",
                        "--host",
                        host,
                        "--port",
                        str(api_port),
                    ],
                    cwd=str(root),
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
            except OSError as exc:
                console.print(f"[red]Could not start API server:[/red] {exc}")
                raise typer.Exit(1) from exc
            health = f"http://{host}:{api_port}/health"
            for _ in range(60):
                if _health_ok(health):
                    break
                if serve_proc.poll() is not None:
                    err = b""
                    if serve_proc.stderr:
                        err = serve_proc.stderr.read()
                    console.print("[red]API server exited early.[/red]")
                    if err.strip():
                        console.print(err.decode(errors="replace").strip())
                    else:
                        console.print(
                            "[dim]Hint: run `uv run sess serve --port "
                            f"{api_port}` in another terminal to see the full log.[/dim]"
                        )
                    raise typer.Exit(1)
                time.sleep(0.1)
            else:
                console.print("[red]Timed out waiting for API; try `sess serve` manually.[/red]")
                serve_proc.terminate()
                raise typer.Exit(1)

    base = f"http://{host}:{api_port}"
    health = f"{base}/health"
    if no_serve and not _health_ok(health):
        console.print(
            f"[red]No API at {health} — start `sess serve --port {api_port}` "
            "or drop --no-serve.[/red]"
        )
        raise typer.Exit(1)

    env = {**os.environ, "SESS_API_BASE": base}
    try:
        result = subprocess.run(
            ["bun", "run", str(tui_dir / "index.ts")],
            cwd=str(tui_dir),
            env=env,
            check=False,
        )
        raise typer.Exit(result.returncode)
    finally:
        if serve_proc is not None and serve_proc.poll() is None:
            serve_proc.terminate()
            try:
                serve_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                serve_proc.kill()


@app.command()
def tui(
    port: int | None = typer.Option(
        None,
        "--port",
        help="Port for the local API when auto-starting the server (default: [server].port)",
    ),
    no_serve: bool = typer.Option(
        False,
        "--no-serve",
        help="Do not start uvicorn; use an API already running (same --port).",
    ),
    strict_port: bool = typer.Option(
        False,
        "--strict-port",
        help="Fail if --port is busy instead of trying the next free port.",
        is_flag=True,
    ),
) -> None:
    """Open the OpenTUI browser (requires Bun and `bun install` in tui/)."""
    settings = get_server_settings()
    api_port = port if port is not None else settings["port"]
    strict = strict_port or settings["strict_port"]
    _run_tui(port=api_port, no_serve=no_serve, strict_port=strict)


@app.command("resume")
def resume(
    port: int | None = typer.Option(
        None,
        "--port",
        help="Port for the local API when auto-starting the server (default: [server].port)",
    ),
    no_serve: bool = typer.Option(
        False,
        "--no-serve",
        help="Do not start uvicorn; use an API already running (same --port).",
    ),
    strict_port: bool = typer.Option(
        False,
        "--strict-port",
        help="Fail if --port is busy instead of trying the next free port.",
        is_flag=True,
    ),
) -> None:
    """Same as `sess tui` — shorthand to reopen the session browser."""
    settings = get_server_settings()
    api_port = port if port is not None else settings["port"]
    strict = strict_port or settings["strict_port"]
    _run_tui(port=api_port, no_serve=no_serve, strict_port=strict)


if __name__ == "__main__":
    app()
