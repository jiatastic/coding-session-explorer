from __future__ import annotations

import chromadb
from sqlalchemy import text

from core import db
from core.models import SearchResult, SourceTool

_MAX_SNIPPET = 180


def _truncate(text: str, length: int = _MAX_SNIPPET) -> str:
    clean = text.strip()
    if len(clean) <= length:
        return clean
    return f"{clean[: length - 3]}..."


def semantic_search(query: str, n_results: int = 10) -> list[SearchResult]:
    chroma_path = str(db.get_db_path().parent / "chroma")
    collection = chromadb.PersistentClient(path=chroma_path).get_or_create_collection("messages")
    response = collection.query(
        query_texts=[query],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )
    results: list[SearchResult] = []

    documents = response.get("documents") or [[]]
    metadatas = response.get("metadatas") or [[]]
    distances = response.get("distances") or [[]]

    if not metadatas[0]:
        return []

    docs = documents[0]
    metas = metadatas[0]
    dists = distances[0]

    for idx, meta in enumerate(metas):
        if not meta:
            continue
        session_id = meta.get("session_id")
        if not isinstance(session_id, str):
            continue
        session = db.get_session(session_id)
        if not session:
            continue
        distance = dists[idx] if idx < len(dists) else None
        score = 1.0 - float(distance or 0.0)
        results.append(
            SearchResult(
                session_id=session_id,
                session_title=session.title,
                source=session.source,
                project_path=session.project_path,
                snippet=_truncate(docs[idx] if docs else ""),
                score=score,
            )
        )

    results.sort(key=lambda item: item.score, reverse=True)
    return results[:n_results]


def fulltext_search(query: str, n_results: int = 10) -> list[SearchResult]:
    query = query.strip()
    if not query:
        return []

    with db.get_engine().connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT m.session_id AS session_id,
                       m.content AS content,
                       fts.rowid AS rowid,
                        s.title AS title,
                        s.source AS source,
                        s.project_path AS project_path
                 FROM messages_fts fts
                 JOIN messagerow m ON m.rowid = fts.rowid
                 JOIN sessionrow s ON s.id = m.session_id
                WHERE fts.content MATCH :query
                ORDER BY rowid
                LIMIT :limit
                """
            ),
            {"query": query, "limit": n_results},
        ).fetchall()

    results: list[SearchResult] = []
    for row in rows:
        try:
            source = SourceTool(row.source)
        except ValueError:
            continue
        results.append(
            SearchResult(
                session_id=row.session_id,
                session_title=row.title,
                source=source,
                project_path=row.project_path,
                snippet=_truncate(row.content or ""),
                score=1.0,
            )
        )

    return results


def search(query: str, n_results: int = 10, mode: str = "auto") -> list[SearchResult]:
    if mode == "fulltext":
        return fulltext_search(query=query, n_results=n_results)
    if mode == "semantic":
        return semantic_search(query=query, n_results=n_results)

    try:
        semantic = semantic_search(query=query, n_results=n_results)
    except Exception:
        semantic = []

    if semantic:
        return semantic
    return fulltext_search(query=query, n_results=n_results)
