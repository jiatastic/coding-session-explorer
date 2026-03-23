from __future__ import annotations

from core import db
from core.config import get_embedding_settings, load_config
from core.crawlers import BaseCrawler, ClaudeCrawler, CodexCrawler, CursorCrawler
from core.embedder import embed_session, set_provider


def index_crawler(crawler: BaseCrawler, force: bool = False) -> dict[str, int]:
    stats = {"new_sessions": 0, "new_messages": 0, "skipped": 0}
    sessions = crawler.crawl_all()
    for session in sessions:
        upserted = db.upsert_session(session)
        if upserted or force:
            embed_session(session)
            stats["new_sessions"] += 1
            stats["new_messages"] += len(session.messages)
        else:
            stats["skipped"] += 1
    return stats


def index_all(force: bool = False) -> dict[str, int]:
    config = load_config()
    db.init_db()
    settings = get_embedding_settings()

    stats = {
        "new_sessions": 0,
        "new_messages": 0,
        "skipped": 0,
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

    for crawler in crawlers:
        crawler_stats = index_crawler(crawler, force=force)
        stats["new_sessions"] += crawler_stats["new_sessions"]
        stats["new_messages"] += crawler_stats["new_messages"]
        stats["skipped"] += crawler_stats["skipped"]

    return stats
