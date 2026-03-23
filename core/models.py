from __future__ import annotations

from datetime import datetime
from enum import StrEnum

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
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    raw_path: str
    messages: list[Message] = Field(default_factory=list)


class SearchResult(BaseModel):
    session_id: str
    session_title: str
    source: SourceTool
    project_path: str | None = None
    snippet: str
    score: float


SearchResultList = list[SearchResult]
