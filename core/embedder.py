from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol, cast

import chromadb

from core.config import get_embedding_settings
from core.models import Message, SourceTool

DATA_DIR = Path.home() / ".coding-sessions"
CHROMA_DIR = DATA_DIR / "chroma"

_openai_client = None
_local_model = None
_provider_settings: dict[str, str | int | bool] = {}


class SessionLike(Protocol):
    id: str
    source: SourceTool
    project_path: str | None
    messages: list[Message]


def set_provider(settings: dict[str, object] | None = None) -> None:
    global _provider_settings
    resolved = settings or get_embedding_settings()
    raw_batch_size = resolved.get("batch_size", 100)
    if isinstance(raw_batch_size, bool):
        batch_size = int(raw_batch_size)
    elif isinstance(raw_batch_size, int):
        batch_size = raw_batch_size
    elif isinstance(raw_batch_size, str):
        try:
            batch_size = int(raw_batch_size)
        except ValueError:
            batch_size = 100
    else:
        batch_size = 100

    _provider_settings = {
        "provider": str(resolved.get("provider", "openai")),
        "model": str(resolved.get("model", "text-embedding-3-small")),
        "batch_size": batch_size,
    }


def _collection() -> chromadb.Collection:
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return client.get_or_create_collection("messages")


def _get_openai_embeddings(
    texts: list[str], model: str, batch_size: int
) -> list[list[float]] | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    global _openai_client
    if _openai_client is None:
        from openai import OpenAI

        _openai_client = OpenAI(api_key=api_key)

    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = _openai_client.embeddings.create(model=model, input=batch)
        for record in response.data:
            vectors.append(record.embedding)
    return vectors


def _get_local_embeddings(texts: list[str]) -> list[list[float]]:
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer

        _local_model = SentenceTransformer("all-MiniLM-L6-v2")
    return [list(map(float, row)) for row in _local_model.encode(texts)]


def _batch_size() -> int:
    return int(_provider_settings.get("batch_size", 100)) if _provider_settings else 100


def _embed_texts(texts: list[str]) -> list[list[float]]:
    settings = _provider_settings if _provider_settings else get_embedding_settings()
    provider = str(settings.get("provider", "openai"))
    model = str(settings.get("model", "text-embedding-3-small"))
    raw_batch_size = settings.get("batch_size", 100)
    if isinstance(raw_batch_size, bool):
        raw_batch_size = int(raw_batch_size)
    try:
        batch_size = int(raw_batch_size)
    except (TypeError, ValueError):
        batch_size = 100

    if provider == "openai":
        openai_vectors = _get_openai_embeddings(texts=texts, model=model, batch_size=batch_size)
        if openai_vectors is not None:
            return openai_vectors

    return _get_local_embeddings(texts=texts)


def _prepare_metadata(session: SessionLike) -> Iterable[dict[str, str | None]]:
    return [
        {
            "session_id": message.session_id,
            "role": message.role.value,
            "source": session.source.value,
            "project_path": session.project_path,
        }
        for message in session.messages
    ]


def embed_session(session: SessionLike) -> int:
    if not session.messages:
        return 0

    texts = [message.content for message in session.messages]
    vectors = _embed_texts(texts)
    collection = _collection()
    collection.upsert(
        ids=[message.id for message in session.messages],
        documents=texts,
        metadatas=list(_prepare_metadata(session)),
        embeddings=cast(Any, vectors),
    )
    return len(session.messages)
