from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlmodel import Field, SQLModel, col, create_engine, select
from sqlmodel import Session as SQLSession

from core.indexing_lock import writer_lock
from core.models import Message, MessageRole, Session, SourceTool

_ENGINE = None
_ENGINE_PATH: str | None = None


def _db_path() -> Path:
    base_dir = Path.home() / ".coding-sessions"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / "sessions.db"


class SessionRow(SQLModel, table=True):
    id: str = Field(primary_key=True)
    source: str
    project_path: str | None = None
    repo_url: str | None = Field(default=None)
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    raw_path: str
    summary: str | None = Field(default=None)
    tokens_input: int | None = Field(default=None)
    tokens_output: int | None = Field(default=None)
    tokens_total: int | None = Field(default=None)
    tokens_context_window: int | None = Field(default=None)
    tokens_estimated: bool = Field(default=False)


class MessageRow(SQLModel, table=True):
    id: str = Field(primary_key=True)
    session_id: str = Field(foreign_key="sessionrow.id", index=True)
    role: str
    content: str
    timestamp: datetime | None = None
    token_count: int | None = None


def get_engine() -> Engine:
    global _ENGINE
    global _ENGINE_PATH

    db_path = _db_path()
    db_url = f"sqlite:///{db_path}"

    if _ENGINE is None or _ENGINE_PATH != str(db_path):
        _ENGINE = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
        )
        _ENGINE_PATH = str(db_path)

        @event.listens_for(_ENGINE, "connect")
        def _sqlite_wal(dbapi_connection: Any, _record: Any) -> None:  # noqa: ANN401
            cur = dbapi_connection.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

    return _ENGINE


def init_db() -> None:
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    _ensure_session_summary_column(engine)
    _ensure_session_repo_url_column(engine)
    _ensure_session_token_columns(engine)
    _ensure_fts(engine)


def _ensure_session_summary_column(engine: Engine) -> None:
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(sessionrow)")).fetchall()
        columns = {row[1] for row in rows}
        if "summary" not in columns:
            conn.execute(text("ALTER TABLE sessionrow ADD COLUMN summary TEXT"))


def _ensure_session_repo_url_column(engine: Engine) -> None:
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(sessionrow)")).fetchall()
        columns = {row[1] for row in rows}
        if "repo_url" not in columns:
            conn.execute(text("ALTER TABLE sessionrow ADD COLUMN repo_url TEXT"))


def _ensure_session_token_columns(engine: Engine) -> None:
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(sessionrow)")).fetchall()
        columns = {row[1] for row in rows}
        if "tokens_input" not in columns:
            conn.execute(text("ALTER TABLE sessionrow ADD COLUMN tokens_input INTEGER"))
        if "tokens_output" not in columns:
            conn.execute(text("ALTER TABLE sessionrow ADD COLUMN tokens_output INTEGER"))
        if "tokens_total" not in columns:
            conn.execute(text("ALTER TABLE sessionrow ADD COLUMN tokens_total INTEGER"))
        if "tokens_context_window" not in columns:
            conn.execute(text("ALTER TABLE sessionrow ADD COLUMN tokens_context_window INTEGER"))
        if "tokens_estimated" not in columns:
            conn.execute(
                text("ALTER TABLE sessionrow ADD COLUMN tokens_estimated INTEGER DEFAULT 0")
            )


def _ensure_fts(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DROP TRIGGER IF EXISTS messages_ai"))
        conn.execute(text("DROP TRIGGER IF EXISTS messages_au"))
        conn.execute(text("DROP TRIGGER IF EXISTS messages_ad"))

        conn.execute(
            text(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
                USING fts5(content, session_id UNINDEXED, tokenize='porter ascii');
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TRIGGER IF NOT EXISTS messages_ai
                AFTER INSERT ON messagerow
                BEGIN
                  INSERT INTO messages_fts(rowid, content, session_id)
                  VALUES (new.rowid, new.content, new.session_id);
                END;
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TRIGGER IF NOT EXISTS messages_au
                AFTER UPDATE ON messagerow
                BEGIN
                    DELETE FROM messages_fts WHERE rowid = old.rowid;
                    INSERT INTO messages_fts(rowid, content, session_id)
                    VALUES (new.rowid, new.content, new.session_id);
                END;
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TRIGGER IF NOT EXISTS messages_ad
                AFTER DELETE ON messagerow
                BEGIN
                    DELETE FROM messages_fts WHERE rowid = old.rowid;
                END;
                """
            )
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messagerow(session_id)")
        )


@contextmanager
def session_scope() -> Iterator[SQLSession]:
    engine = get_engine()
    with SQLSession(engine) as session:
        yield session


def _row_to_session_model(row: SessionRow) -> Session:
    te = getattr(row, "tokens_estimated", None)
    return Session(
        id=row.id,
        source=SourceTool(row.source),
        project_path=row.project_path,
        repo_url=getattr(row, "repo_url", None),
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
        message_count=row.message_count,
        raw_path=row.raw_path,
        summary=row.summary,
        tokens_input=getattr(row, "tokens_input", None),
        tokens_output=getattr(row, "tokens_output", None),
        tokens_total=getattr(row, "tokens_total", None),
        tokens_context_window=getattr(row, "tokens_context_window", None),
        tokens_estimated=bool(te) if te is not None else False,
        messages=[],
    )


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _row_to_message_model(row: MessageRow) -> Message:
    return Message(
        id=row.id,
        session_id=row.session_id,
        role=MessageRole(row.role),
        content=row.content,
        timestamp=row.timestamp,
        token_count=row.token_count,
    )


def upsert_session(session: Session) -> bool:
    with writer_lock:
        return _upsert_session_unlocked(session)


def _upsert_session_unlocked(session: Session) -> bool:
    with session_scope() as db:
        existing = db.get(SessionRow, session.id)

        if existing is not None:
            existing_updated = _as_aware_utc(existing.updated_at)
            session_updated = _as_aware_utc(session.updated_at)
            if (
                existing_updated >= session_updated
                and existing.message_count == session.message_count
                and existing.project_path == session.project_path
                and existing.repo_url == session.repo_url
                and existing.title == session.title
                and getattr(existing, "tokens_input", None) == session.tokens_input
                and getattr(existing, "tokens_output", None) == session.tokens_output
                and getattr(existing, "tokens_total", None) == session.tokens_total
                and getattr(existing, "tokens_context_window", None)
                == session.tokens_context_window
                and bool(getattr(existing, "tokens_estimated", False))
                == session.tokens_estimated
            ):
                return False

        if existing is None:
            db.add(
                SessionRow(
                    id=session.id,
                    source=session.source.value,
                    project_path=session.project_path,
                    repo_url=session.repo_url,
                    title=session.title,
                    created_at=session.created_at,
                    updated_at=session.updated_at,
                    message_count=session.message_count,
                    raw_path=session.raw_path,
                    tokens_input=session.tokens_input,
                    tokens_output=session.tokens_output,
                    tokens_total=session.tokens_total,
                    tokens_context_window=session.tokens_context_window,
                    tokens_estimated=session.tokens_estimated,
                )
            )
        else:
            existing.source = session.source.value
            existing.project_path = session.project_path
            existing.repo_url = session.repo_url
            existing.title = session.title
            existing.created_at = session.created_at
            existing.updated_at = session.updated_at
            existing.message_count = session.message_count
            existing.raw_path = session.raw_path
            existing.summary = None
            existing.tokens_input = session.tokens_input
            existing.tokens_output = session.tokens_output
            existing.tokens_total = session.tokens_total
            existing.tokens_context_window = session.tokens_context_window
            existing.tokens_estimated = session.tokens_estimated
            db.add(existing)

            db.execute(text("DELETE FROM messagerow WHERE session_id = :sid"), {"sid": session.id})
            db.execute(
                text("DELETE FROM messages_fts WHERE session_id = :sid"), {"sid": session.id}
            )

        for message in session.messages:
            db.add(
                MessageRow(
                    id=message.id,
                    session_id=message.session_id,
                    role=message.role.value,
                    content=message.content,
                    timestamp=message.timestamp,
                    token_count=message.token_count,
                )
            )

        db.commit()
        return True


def update_session_summary(session_id: str, summary: str) -> None:
    with writer_lock:
        with session_scope() as db:
            row = db.get(SessionRow, session_id)
            if row is None:
                return
            row.summary = summary
            db.add(row)
            db.commit()


def update_session_title(session_id: str, title: str) -> None:
    with writer_lock:
        with session_scope() as db:
            row = db.get(SessionRow, session_id)
            if row is None:
                return
            row.title = title
            db.add(row)
            db.commit()


def list_session_ids_missing_summary(limit: int = 500) -> list[str]:
    with session_scope() as db:
        statement = (
            select(SessionRow.id)
            .where(col(SessionRow.summary).is_(None))
            .where(SessionRow.message_count > 0)
            .limit(limit)
        )
        rows = db.exec(statement).all()
    return list(rows)


def list_sessions(
    tool: SourceTool | None = None,
    project: str | None = None,
    days: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Session]:
    q = cast(
        Any,
        select(SessionRow)
        .order_by(cast(Any, SessionRow.updated_at).desc())
        .offset(offset)
        .limit(limit),
    )
    if tool is not None:
        q = cast(Any, q).where(SessionRow.source == tool.value)
    if project:
        like = f"%{project}%"
        project_expr = cast(Any, SessionRow.project_path)
        q = cast(Any, q).where(project_expr.is_not(None)).where(project_expr.ilike(like))
    if days is not None:
        cutoff = datetime.now(tz=UTC) - timedelta(days=days)
        q = cast(Any, q).where(cast(Any, SessionRow.created_at) >= cutoff)

    with session_scope() as db:
        rows = db.exec(q).all()

    return [_row_to_session_model(row) for row in rows]


def get_session(session_id: str) -> Session | None:
    with session_scope() as db:
        session_row = db.get(SessionRow, session_id)
        if session_row is None:
            return None

        model = _row_to_session_model(session_row)
        msg_rows = db.exec(
            select(MessageRow)
            .where(MessageRow.session_id == session_id)
            .order_by(
                cast(Any, MessageRow.timestamp).asc().nullslast(),
                MessageRow.id,
            )
        ).all()
        model.messages = [_row_to_message_model(row) for row in msg_rows]
        return model


def get_message_rows_for_session(session_id: str) -> list[MessageRow]:
    with session_scope() as db:
        rows = db.exec(
            select(MessageRow).where(MessageRow.session_id == session_id).order_by(MessageRow.id)
        ).all()
    return list(rows)


def count_sessions(tool: SourceTool | None = None) -> int:
    with session_scope() as db:
        q = select(SessionRow)
        if tool is not None:
            q = q.where(SessionRow.source == tool.value)
        return len(db.exec(q).all())


class HeatmapItem(BaseModel):
    date: str
    tool: SourceTool
    count: int


def get_stats(days: int = 365) -> list[HeatmapItem]:
    cutoff = datetime.now(tz=UTC) - timedelta(days=days)
    with session_scope() as db:
        rows = db.exec(
            select(SessionRow.created_at, SessionRow.source).where(
                cast(Any, SessionRow.created_at) >= cutoff
            )
        ).all()

    buckets = defaultdict(int)
    for created_at, source in rows:
        key = created_at.strftime("%Y-%m-%d")
        buckets[(key, source)] += 1

    data = [
        HeatmapItem(date=date, tool=SourceTool(source), count=count)
        for (date, source), count in sorted(buckets.items())
    ]
    return data


def get_daily_counts(days: int = 365) -> list[dict[str, str | int | SourceTool]]:
    result: list[dict[str, str | int | SourceTool]] = []
    cutoff = datetime.now(tz=UTC) - timedelta(days=days)
    with session_scope() as db:
        rows = db.exec(
            select(SessionRow.source, SessionRow.created_at)
            .where(cast(Any, SessionRow.created_at) >= cutoff)
            .order_by(cast(Any, SessionRow.created_at))
        ).all()

    counts = defaultdict(int)
    for source, created_at in rows:
        key = created_at.strftime("%Y-%m-%d")
        counts[(key, source)] += 1

    for (date, source), count in sorted(counts.items()):
        result.append({"date": date, "tool": source, "count": count})

    return result


def get_summary() -> tuple[int, int, list[SourceTool]]:
    with session_scope() as db:
        sessions = db.exec(select(SessionRow)).all()
        msg_count = db.exec(select(MessageRow.id)).all()

    total_sessions = len(sessions)
    total_messages = len(msg_count)
    tools = sorted({SourceTool(row.source) for row in sessions})
    return total_sessions, total_messages, tools


def get_db_path() -> Path:
    return _db_path()
