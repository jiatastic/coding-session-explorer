from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta

from core import db
from core.config import get_embedding_settings, load_config
from core.crawlers import BaseCrawler, ClaudeCrawler, CodexCrawler, CursorCrawler
from core.embedder import embed_session, set_provider
from core.git_remote import origin_https_url
from core.summarizer import maybe_summarize_session
from core.title_ai import maybe_ai_session_title


def session_in_embedding_window(updated_at: datetime, recent_days: int | None) -> bool:
    """If ``recent_days`` is set, only sessions with ``updated_at`` in the last N days get embed/AI."""
    if recent_days is None:
        return True
    ts = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=UTC)
    cutoff = datetime.now(tz=UTC) - timedelta(days=recent_days)
    return ts >= cutoff


def _crawler_progress_label(crawler: BaseCrawler) -> str:
    name = type(crawler).__name__
    if "Claude" in name:
        return "Claude"
    if "Codex" in name:
        return "Codex"
    if "Cursor" in name:
        return "Cursor"
    return name


def _index_one_path(
    crawler: BaseCrawler,
    path: str,
    force: bool,
    *,
    recent_days: int | None = None,
) -> dict[str, int]:
    stats = {"new_sessions": 0, "new_messages": 0, "skipped": 0, "skipped_heavy": 0}
    try:
        session = crawler.parse(path)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] skipping {path}: {exc}")
        return stats
    if session is None:
        return stats
    session.repo_url = origin_https_url(session.project_path)
    upserted = db.upsert_session(session)
    if upserted or force:
        if session_in_embedding_window(session.updated_at, recent_days):
            embed_session(session)
            stats["new_messages"] += len(session.messages)
            if upserted:
                maybe_summarize_session(session.id)
                maybe_ai_session_title(session.id)
        else:
            stats["skipped_heavy"] += 1
        stats["new_sessions"] += 1
    else:
        stats["skipped"] += 1
    return stats


def index_crawler(
    crawler: BaseCrawler,
    force: bool = False,
    *,
    report_progress: bool = False,
    progress_label: str = "",
    recent_days: int | None = None,
) -> dict[str, int]:
    from core import index_progress

    stats = {"new_sessions": 0, "new_messages": 0, "skipped": 0, "skipped_heavy": 0}
    paths = crawler.discover()
    label = progress_label or type(crawler).__name__
    if report_progress:
        if not paths:
            index_progress.update(crawler=label, current=0, total=0, detail="no files")
        else:
            index_progress.update(crawler=label, current=0, total=len(paths), detail=None)
    for i, path in enumerate(paths):
        if report_progress:
            index_progress.update(crawler=label, current=i + 1, total=len(paths), detail=path)
        frag = _index_one_path(crawler, path, force, recent_days=recent_days)
        for key in stats:
            stats[key] += frag[key]
    return stats


def _merge_stats(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    keys = set(a) | set(b)
    return {k: a.get(k, 0) + b.get(k, 0) for k in keys}


def index_all(
    force: bool = False,
    *,
    report_progress: bool = False,
    recent_days: int | None = None,
) -> dict[str, int]:
    config = load_config()
    db.init_db()
    settings = get_embedding_settings()

    stats: dict[str, int] = {
        "new_sessions": 0,
        "new_messages": 0,
        "skipped": 0,
        "skipped_heavy": 0,
    }

    source_config = config.get("sources", {})
    crawlers: list[BaseCrawler] = []

    if source_config.get("claude", True):
        crawlers.append(ClaudeCrawler())
    if source_config.get("codex", True):
        crawlers.append(CodexCrawler())
    if source_config.get("cursor", True):
        crawlers.append(CursorCrawler())

    set_provider(settings)

    work: list[tuple[BaseCrawler, list[str], str]] = []
    for crawler in crawlers:
        paths = crawler.discover()
        label = _crawler_progress_label(crawler)
        work.append((crawler, paths, label))

    grand_total = sum(len(paths) for _, paths, _ in work)

    if report_progress:
        from core import index_progress

        if grand_total == 0:
            first_label = work[0][2] if work else None
            index_progress.update(crawler=first_label, current=0, total=0, detail="no files")
        else:
            index_progress.update(
                crawler=work[0][2],
                current=0,
                total=grand_total,
                detail=None,
            )

    progress_lock = threading.Lock()
    done_count = [0]

    def bump_progress(label: str, path: str) -> None:
        if not report_progress:
            return
        from core import index_progress

        with progress_lock:
            done_count[0] += 1
            index_progress.update(
                crawler=label,
                current=done_count[0],
                total=grand_total,
                detail=path,
            )

    def run_worker(item: tuple[BaseCrawler, list[str], str]) -> dict[str, int]:
        crawler, paths, label = item
        local = {"new_sessions": 0, "new_messages": 0, "skipped": 0, "skipped_heavy": 0}
        for path in paths:
            bump_progress(label, path)
            frag = _index_one_path(crawler, path, force, recent_days=recent_days)
            for key in local:
                local[key] += frag[key]
        return local

    max_workers = max(1, len(work))
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="sess-index") as pool:
        futures = [pool.submit(run_worker, item) for item in work]
        for fut in as_completed(futures):
            stats = _merge_stats(stats, fut.result())

    return stats
