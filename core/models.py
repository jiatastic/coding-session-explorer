from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class SourceTool(StrEnum):
    CLAUDE = "claude"
    CODEX = "codex"
    CURSOR = "cursor"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class Message(BaseModel):
    id: str
    session_id: str
    role: MessageRole
    content: str
    timestamp: datetime | None = None
    token_count: int | None = None


class Session(BaseModel):
    id: str
    source: SourceTool
    project_path: str | None
    repo_url: str | None = None
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    raw_path: str
    summary: str | None = None
    tokens_input: int | None = None
    tokens_output: int | None = None
    tokens_total: int | None = None
    tokens_context_window: int | None = None
    tokens_estimated: bool = False
    messages: list[Message] = Field(default_factory=list)


class SearchResult(BaseModel):
    session_id: str
    session_title: str
    source: SourceTool
    project_path: str | None = None
    repo_url: str | None = None
    snippet: str
    score: float


SearchResultList = list[SearchResult]


class OpenAIKeyStatus(BaseModel):
    """Effective OpenAI credential state for the local API (never exposes the key)."""

    configured: bool
    source: Literal["env", "file", "none"]
    has_stored_key: bool


class OpenAIKeyBody(BaseModel):
    """PUT body: set api_key to empty string to remove stored key only."""

    api_key: str = ""
