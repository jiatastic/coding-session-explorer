from __future__ import annotations

from pathlib import Path

try:
    from dotenv import load_dotenv

    _repo_root = Path(__file__).resolve().parents[1]
    load_dotenv(_repo_root / ".env")
    load_dotenv()
except ImportError:
    pass

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from core import db, index_progress
from core import search as search_module
from core.indexer import index_all
from core.models import OpenAIKeyBody, OpenAIKeyStatus, SearchResult, Session, SourceTool
from core.resume import SessionResumeCommand, build_resume_command
from core.secrets import (
    get_openai_api_key,
    get_stored_openai_api_key,
    openai_key_source,
    set_stored_openai_api_key,
)

app = FastAPI(title="coding-session-explorer")


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://127.0.0.1",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/sessions")
def list_sessions(
    tool: str | None = None,
    project: str | None = None,
    days: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = 0,
) -> list[Session]:
    db.init_db()
    tool_value = None
    if tool is not None:
        try:
            tool_value = SourceTool(tool)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid tool") from exc

    return db.list_sessions(tool=tool_value, project=project, days=days, limit=limit, offset=offset)


@app.get("/sessions/{session_id}")
def get_session(session_id: str) -> Session:
    db.init_db()
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@app.get("/settings/openai")
def get_openai_key_settings() -> OpenAIKeyStatus:
    return OpenAIKeyStatus(
        configured=bool(get_openai_api_key()),
        source=openai_key_source(),
        has_stored_key=bool(get_stored_openai_api_key()),
    )


@app.put("/settings/openai")
def put_openai_key_settings(body: OpenAIKeyBody) -> OpenAIKeyStatus:
    set_stored_openai_api_key(body.api_key.strip() or None)
    return get_openai_key_settings()


@app.get("/sessions/{session_id}/resume")
def get_session_resume(session_id: str) -> SessionResumeCommand:
    db.init_db()
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return build_resume_command(session)


@app.get("/search")
def run_search(
    q: str,
    limit: int = Query(default=10, ge=1, le=100),
    mode: str = Query(default="auto"),
) -> list[SearchResult]:
    if mode not in {"auto", "semantic", "fulltext"}:
        raise HTTPException(status_code=400, detail="invalid mode")
    return search_module.search(query=q, n_results=limit, mode=mode)


@app.get("/stats")
def get_stats(year: int | None = None):
    rows = db.get_daily_counts(days=3650)
    if year is None:
        return rows
    filtered = [row for row in rows if str(row["date"]).startswith(f"{year}-")]
    return filtered


def _background_index(recent_days: int | None = None) -> None:
    try:
        stats = index_all(
            force=True, report_progress=True, recent_days=recent_days
        )
        index_progress.finish(stats)
    except Exception as exc:  # noqa: BLE001
        index_progress.fail(str(exc))


@app.get("/index/status")
def index_status() -> dict:
    return index_progress.snapshot()


@app.post("/index")
def trigger_index(
    background_tasks: BackgroundTasks,
    recent_days: int | None = Query(
        default=None,
        ge=1,
        le=36500,
        description="Only embed + AI for sessions updated in the last N days.",
    ),
) -> dict[str, str]:
    db.init_db()
    if index_progress.is_running():
        raise HTTPException(status_code=409, detail="index already running")
    index_progress.reset_running()
    background_tasks.add_task(_background_index, recent_days)
    return {"status": "queued"}
