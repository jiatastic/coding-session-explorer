from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from core import db
from core.models import SearchResult, Session, SourceTool


def _short_id(value: str, length: int = 8) -> str:
    return value[:length]


def _tool_style(tool: SourceTool) -> str:
    return {
        SourceTool.CLAUDE: "blue",
        SourceTool.CODEX: "green",
        SourceTool.CURSOR: "magenta",
    }[tool]


def _tool_cell(tool: SourceTool) -> str:
    return f"[{_tool_style(tool)}]{tool.value.title()}[/{_tool_style(tool)}]"


def _truncate(value: str, size: int) -> str:
    clean = value.strip().replace("\n", " ")
    if len(clean) <= size:
        return clean
    return f"{clean[: size - 1]}..."


def render_session_table(sessions: list[Session]) -> Table:
    table = Table(show_header=True, box=box.SIMPLE)
    table.add_column("ID (short)")
    table.add_column("Tool")
    table.add_column("Project")
    table.add_column("Title")
    table.add_column("Messages", justify="right")
    table.add_column("Date")

    for session in sessions:
        created = session.created_at.astimezone(UTC).strftime("%Y-%m-%d")
        project = session.project_path or "-"
        table.add_row(
            _short_id(session.id),
            _tool_cell(session.source),
            _truncate(project, 36),
            session.title,
            str(session.message_count),
            created,
        )

    return table


def render_summary(total_sessions: int, total_messages: int, skipped: int) -> Table:
    table = Table(show_header=False, box=box.ROUNDED)
    table.add_column("Metric")
    table.add_column("Count", justify="right")
    table.add_row("sessions indexed", str(total_sessions))
    table.add_row("messages embedded", str(total_messages))
    table.add_row("skipped", str(skipped))
    return table


def render_message_view(session: Session) -> None:
    console = Console()
    console.rule(f"[bold]{session.title}[/bold] · [dim]{session.id}[/dim]")

    if session.tokens_total is not None:
        est = " (estimated ~4 chars/token)" if session.tokens_estimated else ""
        parts = [
            f"input {session.tokens_input}",
            f"output {session.tokens_output}",
            f"total {session.tokens_total}",
        ]
        if session.tokens_context_window is not None:
            pct = min(
                100.0,
                (session.tokens_total / session.tokens_context_window) * 100,
            )
            parts.append(f"context {session.tokens_context_window} (~{pct:.1f}% used)")
        console.print(
            Panel(
                " · ".join(str(p) for p in parts) + est,
                title="[bold]Tokens[/bold]",
                border_style="dim",
            )
        )

    if session.summary:
        console.print(
            Panel(
                session.summary,
                title="[bold]AI summary[/bold]",
                border_style="dim",
            )
        )

    for message in session.messages:
        border = {
            "user": "cyan",
            "assistant": "blue",
            "system": "grey50",
            "tool": "yellow",
        }.get(message.role.value, "white")
        rendered = Markdown(message.content, code_theme="monokai")
        timestamp = message.timestamp.astimezone(UTC).isoformat() if message.timestamp else ""
        title = f"{message.role.value}"
        if timestamp:
            title = f"{title} • {timestamp}"
        console.print(
            Panel(
                rendered,
                title=title,
                border_style=border,
                expand=False,
            )
        )


def render_search_table(results: list[SearchResult]) -> Table:
    table = Table(show_header=True, box=box.ROUNDED)
    table.add_column("#", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("Tool")
    table.add_column("Project")
    table.add_column("Title")
    table.add_column("Snippet")

    for index, result in enumerate(results, start=1):
        score = f"{result.score:.4f}"
        project = result.project_path or "-"
        table.add_row(
            str(index),
            score,
            _tool_cell(result.source),
            _truncate(project, 24),
            result.session_title,
            _truncate(result.snippet, 120),
        )

    return table


def _build_week_buckets(dates: Iterable[str], year: int | None = None) -> list[int]:
    today = datetime.now(tz=UTC)
    if year is None:
        end = today
        start = end - timedelta(days=364)
    else:
        start = datetime(year, 1, 1, tzinfo=UTC)
        end = datetime(year, 12, 31, tzinfo=UTC)
        if year == today.year:
            end = today

    buckets: dict[int, int] = {w: 0 for w in range(52)}
    for date in dates:
        parsed = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
        if parsed < start or parsed > end:
            continue
        idx = int((parsed - start).days / 7)
        if idx in buckets:
            buckets[idx] += 1
    return [buckets[key] for key in sorted(buckets)]


def render_stats(year: int | None = None) -> Table:
    rows = db.get_daily_counts(days=3650)

    tool_dates: dict[SourceTool, list[str]] = {
        SourceTool.CLAUDE: [],
        SourceTool.CODEX: [],
        SourceTool.CURSOR: [],
    }

    for row in rows:
        raw_tool = row["tool"]
        if isinstance(raw_tool, SourceTool):
            tool = raw_tool
        else:
            tool = SourceTool(str(raw_tool))
        date = str(row["date"])
        tool_dates[tool].append(date)

    max_count = 1
    for values in tool_dates.values():
        if not values:
            continue
        buckets = _build_week_buckets(values, year=year)
        max_count = max(max_count, max(buckets))
        if max_count > 5:
            break

    table = Table(show_header=True, box=box.HEAVY, title="[bold]Activity[/bold]")
    table.add_column("Tool")
    table.add_column("Yearly")

    for tool in (SourceTool.CLAUDE, SourceTool.CODEX, SourceTool.CURSOR):
        buckets = _build_week_buckets(tool_dates[tool], year=year)
        cells = []
        for count in buckets:
            intensity = min(5, int(round((count / max_count) * 5)))
            color = ["grey30", "blue", "blue3", "turquoise2", "spring_green1", "green"][intensity]
            cells.append(f"[{color}]█[/{color}]")
        row = "".join(cells)
        table.add_row(tool.value, row)

    return table
