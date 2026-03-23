from __future__ import annotations

import logging
from pathlib import Path

import typer
import uvicorn
from rich.console import Console
from rich.live import Live
from rich.logging import RichHandler
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskID, TextColumn, TimeElapsedColumn

from cli import display
from core import db
from core import search as search_module
from core.config import get_embedding_settings, load_config
from core.crawlers import ClaudeCrawler, CodexCrawler, CursorCrawler
from core.embedder import set_provider
from core.indexer import index_crawler
from core.models import SourceTool
from core.watcher import create_observer

app = typer.Typer(help="Session explorer")
console = Console()
log = logging.getLogger("sess")


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        _run_list()
        console.print("[dim]Tip: sess --help for all commands (index, view, search, stats, watch, serve).[/dim]")


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


@app.command()
def index(
    force: bool = typer.Option(False, "--force", help="Reindex even unchanged sessions"),
) -> None:
    embedding_settings = get_embedding_settings()
    set_provider(embedding_settings)

    source_settings = load_config().get("sources", {})
    crawlers = []
    if source_settings.get("claude", True):
        crawlers.append(("Claude", ClaudeCrawler()))
    if source_settings.get("codex", True):
        crawlers.append(("Codex", CodexCrawler()))
    if source_settings.get("cursor", True):
        crawlers.append(("Cursor", CursorCrawler()))

    db.init_db()
    aggregate = {"new_sessions": 0, "new_messages": 0, "skipped": 0}

    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        master = progress.add_task("crawlers", total=len(crawlers))
        for label, crawler in crawlers:
            task_id: TaskID = progress.add_task(f"indexing {label}", total=1)
            crawler_stats = index_crawler(crawler, force=force)
            progress.update(task_id, completed=1)
            progress.remove_task(task_id)
            for key, value in crawler_stats.items():
                aggregate[key] += value
            progress.update(master, advance=1)

    console.print(
        display.render_summary(
            aggregate["new_sessions"], aggregate["new_messages"], aggregate["skipped"]
        )
    )


def _run_list(
    tool: str | None = None,
    project: str | None = None,
    days: int | None = None,
    limit: int = 100,
) -> None:
    db.init_db()
    selected = _resolve_tool(tool)
    sessions = db.list_sessions(tool=selected, project=project, days=days, limit=limit)
    if not sessions:
        console.print("[yellow]No sessions found[/yellow]")
        console.print("[dim]Run [bold]sess index[/bold] to import Claude, Codex, and Cursor history.[/dim]")
        return
    console.print(display.render_session_table(sessions))


@app.command("list")
def list_cmd(
    tool: str | None = typer.Option(None, "--tool", help="Filter by claude|codex|cursor"),
    project: str | None = typer.Option(None, "--project", help="Filter by project path"),
    days: int | None = typer.Option(None, "--days", help="Only sessions updated within N days"),
    limit: int = typer.Option(100, "--limit", help="Max sessions to show"),
) -> None:
    _run_list(tool=tool, project=project, days=days, limit=limit)


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

    db.init_db()
    upserted = db.upsert_session(parsed)
    if upserted:
        from core.embedder import embed_session

        embed_session(parsed)
    log.info("indexed %s (%s)", target, "updated" if upserted else "unchanged")


@app.command()
def watch() -> None:
    logging.basicConfig(
        level=logging.INFO, handlers=[RichHandler(rich_tracebacks=True)], format="%(message)s"
    )
    db.init_db()

    home = Path.home()
    paths = [
        str(home / ".claude" / "transcripts"),
        str(home / ".codex" / "sessions"),
        str(home / ".cursor" / "chats"),
    ]
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


if __name__ == "__main__":
    app()
