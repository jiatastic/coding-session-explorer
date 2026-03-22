from __future__ import annotations

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from core import db
from core import search as search_module
from core.indexer import index_all
from core.models import SearchResult, Session, SourceTool

app = FastAPI(title="coding-session-explorer")


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
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


@app.post("/index")
def trigger_index(background_tasks: BackgroundTasks) -> dict[str, str]:
    db.init_db()
    background_tasks.add_task(index_all, True)
    return {"status": "queued"}
