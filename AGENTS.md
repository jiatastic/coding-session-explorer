# AGENTS.md — Implementation Spec

This file is the ground truth for implementing `coding-session-explorer`.
Read this fully before writing any code. Follow each phase in order.

---

## 0. Context

This project indexes AI coding session history from three tools on the local machine:

| Tool | Raw data path | Format |
|---|---|---|
| Claude Code | `~/.claude/transcripts/*.jsonl` | JSONL, one message per line |
| Claude Code (projects) | `~/.claude/projects/**/*.jsonl` | JSONL, first line often `{"type":"summary","summary":"..."}` |
| Codex CLI | `~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl` | JSONL, first line is `session_meta` |
| Cursor | `~/.cursor/chats/<proj-hash>/<session-uuid>/store.db` | SQLite, `meta` table + `blobs` table |

Confirmed sample formats:

**Claude transcript line:**
```json
{"type": "user", "timestamp": "2026-03-21T05:06:31.711Z", "content": "hello"}
```

**Codex session_meta line:**
```json
{
  "timestamp": "2026-03-07T00:31:54.596Z",
  "type": "session_meta",
  "payload": {
    "id": "4557bbea-bceb-464a-8265-55005585cb4c",
    "timestamp": "2026-03-07T00:31:54.564Z",
    "cwd": "/Users/haoxiangjia/Documents/GitHub/api_v2",
    "originator": "codex_cli_rs",
    "cli_version": "0.36.0"
  }
}
```

**Cursor meta table (key=0, value is hex-decoded JSON):**
```json
{
  "agentId": "9ac15289-9e6f-47de-a304-6ccbfc1bac9b",
  "latestRootBlobId": "aea374854...",
  "name": "Email Builder Guide",
  "mode": "default",
  "createdAt": 1768719687240,
  "lastUsedModel": "gpt-5.2-codex"
}
```

All indexed data is stored in `~/.coding-sessions/`.

---

## 1. Project Structure

```
coding-session-explorer/
├── core/
│   ├── __init__.py
│   ├── models.py          # Pydantic data models (Session, Message)
│   ├── db.py              # SQLite setup via SQLModel
│   ├── embedder.py        # Embedding generation + ChromaDB writes
│   ├── search.py          # Semantic search (ChromaDB) + FTS fallback (SQLite FTS5)
│   ├── watcher.py         # watchdog FileSystemEventHandler
│   └── crawlers/
│       ├── __init__.py
│       ├── base.py        # Abstract BaseCrawler
│       ├── claude.py      # Claude JSONL crawler
│       ├── codex.py       # Codex JSONL crawler
│       └── cursor.py      # Cursor SQLite crawler
├── cli/
│   ├── __init__.py
│   ├── main.py            # Typer app — all `sess` subcommands
│   └── display.py         # Rich rendering helpers
├── server/
│   ├── __init__.py
│   └── main.py            # FastAPI JSON API (TUI + optional tools)
├── tui/
│   ├── package.json       # Bun + @opentui/core
│   ├── index.ts           # OpenTUI entry (sessions list, search, detail)
│   └── tsconfig.json
├── pyproject.toml
├── .gitignore
├── README.md
└── AGENTS.md
```

---

## 2. Data Models

Define in `core/models.py` using Pydantic v2:

```python
from enum import Enum
from datetime import datetime
from pydantic import BaseModel

class SourceTool(str, Enum):
    CLAUDE = "claude"
    CODEX = "codex"
    CURSOR = "cursor"

class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"

class Message(BaseModel):
    id: str                     # sha256(session_id + index)
    session_id: str
    role: MessageRole
    content: str
    timestamp: datetime | None
    token_count: int | None = None

class Session(BaseModel):
    id: str                     # stable hash of source file path
    source: SourceTool
    project_path: str | None    # cwd / repo path, None if unknown
    title: str                  # summary or auto-generated
    created_at: datetime
    updated_at: datetime
    message_count: int
    raw_path: str               # absolute path to source file
    messages: list[Message] = []
```

---

## 3. Database Schema

Define in `core/db.py` using SQLModel + raw SQLite for FTS5.

### SQLModel tables

```python
# sessions table
class SessionRow(SQLModel, table=True):
    id: str = Field(primary_key=True)
    source: str
    project_path: str | None = None
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int
    raw_path: str

# messages table
class MessageRow(SQLModel, table=True):
    id: str = Field(primary_key=True)
    session_id: str = Field(foreign_key="sessionrow.id", index=True)
    role: str
    content: str
    timestamp: datetime | None = None
    token_count: int | None = None
```

### FTS5 virtual table (run after SQLModel creates tables)

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
USING fts5(content, session_id UNINDEXED, tokenize='porter ascii');

-- Keep in sync via triggers
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messagerow BEGIN
  INSERT INTO messages_fts(rowid, content, session_id)
  VALUES (new.rowid, new.content, new.session_id);
END;
```

Database file: `~/.coding-sessions/sessions.db`

---

## 4. Crawlers

### `core/crawlers/base.py`

```python
from abc import ABC, abstractmethod
from core.models import Session

class BaseCrawler(ABC):
    @abstractmethod
    def discover(self) -> list[str]:
        """Return list of raw file/db paths to process."""
        ...

    @abstractmethod
    def parse(self, path: str) -> Session | None:
        """Parse a single source file/db into a Session. Return None to skip."""
        ...

    def crawl_all(self) -> list[Session]:
        sessions = []
        for path in self.discover():
            try:
                s = self.parse(path)
                if s:
                    sessions.append(s)
            except Exception as e:
                print(f"[warn] skipping {path}: {e}")
        return sessions
```

### `core/crawlers/claude.py`

- `discover()`: glob `~/.claude/transcripts/*.jsonl` + `~/.claude/projects/**/*.jsonl`
- `parse(path)`:
  - Read all lines, parse JSON
  - Skip lines where `type` is `summary` — use its `summary` field as the session title
  - Collect lines where `type` in `["user", "assistant"]` as messages
  - `session.id` = `sha256(path)`
  - `project_path`: infer from the parent directory name if under `projects/` (reverse the `-Users-haoxiangjia-...` naming convention: replace `-` with `/`, strip leading `/`)
  - `created_at`: first message timestamp

### `core/crawlers/codex.py`

- `discover()`: glob `~/.codex/sessions/**/*.jsonl` (recursive)
- `parse(path)`:
  - First line must have `"type": "session_meta"` — extract `payload.id`, `payload.cwd`, `payload.timestamp`
  - Remaining lines: collect messages with role from `type` field
  - `session.id` = `payload.id` from session_meta (use this as stable ID)
  - `project_path` = `payload.cwd`
  - `title` = first user message content truncated to 80 chars, or filename

### `core/crawlers/cursor.py`

- `discover()`: glob `~/.cursor/chats/**/store.db`
- `parse(path)`:
  - Open SQLite, query `SELECT key, value FROM meta`
  - Key `0` value is hex-encoded bytes → decode → parse JSON → extract `name`, `createdAt`, `lastUsedModel`
  - `session.id` = `agentId` from decoded JSON
  - `title` = `name` field
  - `created_at` = `createdAt` (milliseconds epoch)
  - `project_path` = None (infer from parent directory hash if possible, skip for now)
  - **Blobs**: attempt to decode blob data as JSON. If it fails, skip message content — still index the session with metadata only (title + timestamp). Log a warning. Do NOT crash.
  - `message_count` = number of blob rows

---

## 5. Indexer

`core/indexer.py` runs **one enabled crawler per thread** (`ThreadPoolExecutor`): Claude / Codex / Cursor `discover()` in parallel, each worker walks its file list independently. **SQLite + Chroma writes are serialized** via `core/indexing_lock.writer_lock` (WAL + `busy_timeout` on connections) so parallel parse + embed stays safe.

`index_all(force, report_progress=…)` merges per-source stats; `index_crawler()` remains for single-source sequential use. Progress uses a **global file counter** across sources (`current` / `total` = total files all crawlers).

Use `updated_at` to detect whether a session needs re-embedding (compare file mtime with stored `updated_at`).

---

## 6. Embedder

In `core/embedder.py`:

- Use `openai.embeddings.create(model="text-embedding-3-small", input=[...])` in batches of 100
- Fall back to `sentence_transformers.SentenceTransformer("all-MiniLM-L6-v2")` if `OPENAI_API_KEY` is not set
- ChromaDB collection name: `"messages"`
- Document ID: `message.id`
- Document text: `message.content`
- Metadata stored per document: `{"session_id": ..., "role": ..., "source": ..., "project_path": ...}`
- Persist ChromaDB at `~/.coding-sessions/chroma/`

---

## 7. Search

In `core/search.py`:

```python
def semantic_search(query: str, n_results: int = 10) -> list[SearchResult]:
    """Vector search via ChromaDB, returns session snippets with scores."""

def fulltext_search(query: str, n_results: int = 10) -> list[SearchResult]:
    """SQLite FTS5 fallback — used when embeddings unavailable."""

def search(query: str, n_results: int = 10, mode: str = "auto") -> list[SearchResult]:
    """mode: 'semantic' | 'fulltext' | 'auto' (semantic with FTS fallback)"""
```

`SearchResult` model:
```python
class SearchResult(BaseModel):
    session_id: str
    session_title: str
    source: SourceTool
    project_path: str | None
    snippet: str          # the matching message content (truncated)
    score: float          # cosine similarity or FTS rank
```

---

## 8. CLI (`sess`)

In `cli/main.py` using **Typer**. Register as `sess` entrypoint in `pyproject.toml`.

### Commands

```
sess index [--force] [--summarize-missing]
```
- Runs `index_all` (parallel per source); with `--force`, re-embeds even unchanged sessions
- Shows a Rich `Live` line from `index_progress` (crawler label + global file count); prints summary table
- `--summarize-missing`: after indexing, backfill AI summaries (requires `OPENAI_API_KEY`)

```
sess reindex [--summarize-missing]
```
- Shortcut for `sess index --force` (full reindex)

```
sess list [--tool claude|codex|cursor] [--project PATH] [--days N] [--limit N]
```
- Rich Table with columns: `ID (short)`, `Tool`, `Project`, `Title`, `Messages`, `Date`
- Tool column uses colored labels: Claude=blue, Codex=green, Cursor=purple

```
sess view <session-id>
```
- Renders full conversation using `rich.markdown.Markdown`
- Each message in a `rich.panel.Panel` with role as title, colored border
- Code blocks auto-highlighted via `rich.syntax.Syntax`

```
sess search <query> [--limit N] [--mode semantic|fulltext]
```
- Calls `search()`, renders results as Rich table
- Shows: rank, score, tool, project, title, snippet (truncated to 120 chars)

```
sess stats [--year YYYY]
```
- Prints a GitHub-style contribution heatmap using Unicode block chars
- One row per tool (Claude / Codex / Cursor), columns = weeks
- Uses `rich` for color

```
sess watch
```
- Runs `watchdog` observer on `~/.claude/transcripts/`, `~/.codex/sessions/`, `~/.cursor/chats/`
- On new/modified `.jsonl` or `.db` file: re-parse and upsert that single file
- Prints a live Rich log

```
sess serve [--port 8000]
```
- Starts FastAPI via uvicorn (for `sess tui --no-serve` or other API clients).

```
sess                    # no subcommand → same as sess tui (quick resume)
sess resume             # explicit alias
sess tui [--port 8000] [--no-serve]
```
- Launches the OpenTUI (`tui/index.ts` via Bun). Default: starts uvicorn on the same port if `/health` is not already up.
- Requires [Bun](https://bun.sh/) and `bun install` in `tui/`.

---

## 9. FastAPI Server

In `server/main.py`. Imports directly from `core/`.

### Endpoints

```
GET  /sessions              → list sessions (query params: tool, project, days, limit, offset)
GET  /sessions/{id}         → get single session with messages
GET  /search?q=&limit=&mode= → semantic/fulltext search
GET  /stats                 → heatmap data (sessions per day per tool)
POST /index                 → trigger reindex (background task)
GET  /health                → {"status": "ok"}
```

All responses use Pydantic models. Enable CORS for `localhost` / `127.0.0.1` if needed for browser-based tools.

---

## 10. Terminal UI (OpenTUI + Bun)

Interactive UI lives in `tui/` using [@opentui/core](https://opentui.com/) (native Zig core, TypeScript API).

### Setup

```bash
cd tui
bun install
```

### Runtime

- `sess` (default), `sess resume`, and `sess tui` set `SESS_API_BASE` (default `http://127.0.0.1:8000`) and run `bun run index.ts`.
- The TUI calls the same FastAPI routes as the CLI-backed workflows: `GET /sessions`, `GET /sessions/{id}`, `GET /search`, `GET /health`.

### UX targets (MVP)

- Session list (`Select`) + semantic search field (`Input` + Enter → `GET /search`)
- List filters row: **Agent** (`claude` \| `codex` \| `cursor`, empty = all), **Project** (substring → `GET /sessions?project=`), **Days** (max age → `?days=`), Enter applies; semantic hits are client-filtered by agent + project when a query is active
- Session detail (`ScrollBox` of messages); `b` returns to list (restores filters + search text)
- Tokyonight-style colors; Ctrl+C exits (renderer `exitOnCtrlC`)

---

## 11. Configuration

`~/.coding-sessions/config.toml` (created on first `sess index`):

```toml
[embedding]
provider = "openai"           # "openai" | "local"
model = "text-embedding-3-small"
batch_size = 100

[sources]
claude = true
codex = true
cursor = true

[server]
port = 8000
host = "127.0.0.1"

[summarization]
enabled = true
model = "gpt-4o-mini"
title_ai = false   # true + OPENAI_API_KEY → AI session titles after upsert (still prefixed with project basename when set)
```

Read with `tomllib` (stdlib in Python 3.11+). Respect `OPENAI_API_KEY` env var. Override `title_ai` with `TITLE_AI_ENABLED=true|false`.

---

## 12. pyproject.toml

```toml
[project]
name = "coding-session-explorer"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "typer>=0.12",
    "rich>=13",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlmodel>=0.0.21",
    "chromadb>=0.5",
    "openai>=1.40",
    "sentence-transformers>=3.0",
    "watchdog>=4.0",
    "pydantic>=2.7",
    "httpx>=0.27",
]

[project.optional-dependencies]
dev = ["pytest", "ruff", "pyright"]

[project.scripts]
sess = "cli.main:app"

[tool.ruff]
line-length = 100
target-version = "py312"
```

---

## 13. Implementation Order

Follow this order exactly:

1. `core/models.py` — Pydantic models
2. `core/db.py` — SQLite + FTS5 setup
3. `core/crawlers/base.py` — abstract crawler
4. `core/crawlers/claude.py` — Claude parser (most data available, test first)
5. `core/crawlers/codex.py` — Codex parser
6. `core/crawlers/cursor.py` — Cursor parser (metadata only first; blob decoding later)
7. `core/indexer.py` — orchestrate crawlers + db upsert
8. `core/embedder.py` — embedding + ChromaDB
9. `core/search.py` — semantic + FTS search
10. `cli/display.py` — Rich helpers
11. `cli/main.py` — all Typer commands
12. `server/main.py` — FastAPI endpoints
13. `tui/` — OpenTUI (`bun install`, `index.ts` → `sess` / `sess tui`)

After each step: run `pyright` (types) and `ruff check` (linting) before moving on.

---

## 14. Testing

- Use `pytest`. Test files in `tests/`.
- Unit test each crawler with fixture files in `tests/fixtures/` (small sample JSONL / SQLite files)
- Integration test: run `sess index` against fixtures, assert DB row counts
- No mocking of the filesystem — use real temp dirs via `tmp_path`

---

## 15. Known Constraints

- **Cursor blobs**: blob format (MessagePack or protobuf) is not publicly documented. Phase 1: index metadata only. Future: reverse-engineer via hex dump.
- **Claude projects path decoding**: project directories use `-` as path separator (e.g. `-Users-haoxiangjia-Documents-GitHub-api-v2`). Decode by replacing `-` with `/` and prepending `/`. Handle ambiguous `-` in directory names gracefully.
- **Incremental indexing**: use file `mtime` vs stored `updated_at` to skip unchanged files. Do NOT re-embed on every `sess index`.
- **Privacy**: all data stays local. Never send session content to any external service except the configured embedding API.
