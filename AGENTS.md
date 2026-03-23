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
│   └── main.py            # FastAPI app (used as Tauri sidecar)
├── desktop/
│   ├── src-tauri/
│   │   ├── Cargo.toml
│   │   ├── tauri.conf.json
│   │   └── src/
│   │       └── main.rs
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx         # Dashboard + heatmap
│   │   │   ├── sessions/
│   │   │   │   ├── page.tsx     # Session list
│   │   │   │   └── [id]/
│   │   │   │       └── page.tsx # Session detail / conversation viewer
│   │   │   └── search/
│   │   │       └── page.tsx     # Semantic search
│   │   └── components/
│   │       ├── HeatMap.tsx
│   │       ├── SessionCard.tsx
│   │       ├── MessageViewer.tsx
│   │       └── SearchResult.tsx
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   └── next.config.ts
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

Create `core/indexer.py`:

```python
def index_all(force: bool = False) -> dict:
    """Run all crawlers, upsert into SQLite, generate embeddings for new messages."""
    from core.crawlers.claude import ClaudeCrawler
    from core.crawlers.codex import CodexCrawler
    from core.crawlers.cursor import CursorCrawler

    crawlers = [ClaudeCrawler(), CodexCrawler(), CursorCrawler()]
    stats = {"new_sessions": 0, "new_messages": 0, "skipped": 0}

    for crawler in crawlers:
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
```

Use `updated_at` to detect whether a session needs re-embedding (compare file mtime with stored `updated_at`).

---

## 6. Embedder

In `core/embedder.py`:

- Use `openai.embeddings.create(model="text-embedding-3-small", input=[...])` in batches of 100
- Fall back to `sentence_transformers.SentenceTransformer("all-MiniLM-L6-v2")` if no OpenAI key is set in `~/.coding-sessions/config.toml` (`[embedding]` → `openai_api_key` or `api_key`)
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
sess index [--force]
```
- Runs `index_all()`, shows a Rich progress bar per crawler
- Prints summary table: sessions indexed, messages embedded, skipped

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
- Starts FastAPI via uvicorn. Used by the Tauri desktop app.

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

All responses use Pydantic models. Enable CORS for `localhost` (Tauri webview).

---

## 10. Desktop App (Tauri v2 + React)

### Setup

```bash
cd desktop
npx create-tauri-app@latest . --template next --manager npm
npm install
```

Use **Next.js 14** (App Router) inside Tauri. Tailwind CSS + shadcn/ui.

### Tauri sidecar config (`src-tauri/tauri.conf.json`)

Configure `sess serve` as a sidecar binary that Tauri spawns on startup and kills on exit:

```json
{
  "bundle": {
    "externalBin": ["../../../bin/sess"]
  },
  "app": {
    "withGlobalTauri": true
  }
}
```

In `src-tauri/src/main.rs`, spawn the sidecar on app ready and store the child process handle. Kill it on window close.

### Pages

**`app/page.tsx` — Dashboard**
- Fetch `GET /stats` and render `<HeatMap />` (one row per tool)
- Show summary cards: total sessions, total messages, tools active
- Recent sessions list (last 10)

**`app/sessions/page.tsx` — Session List**
- Fetch `GET /sessions` with filter params
- Render `<SessionCard />` grid
- Filter sidebar: tool checkboxes, date range picker, project search box

**`app/sessions/[id]/page.tsx` — Session Detail**
- Fetch `GET /sessions/{id}`
- Render `<MessageViewer />` — message bubbles with Markdown + syntax highlight (use `react-markdown` + `rehype-highlight`)
- Show session metadata in a side panel (tool, project, date, model)

**`app/search/page.tsx` — Search**
- Search input with debounce (300ms)
- Fetch `GET /search?q=`
- Render `<SearchResult />` cards with snippet highlight and link to session detail

### Components

**`HeatMap.tsx`**
- Props: `data: { date: string; tool: SourceTool; count: number }[]`
- Render 52-week grid using `<div>` cells, Tailwind colors per tool
- Tooltip on hover showing date + count

**`SessionCard.tsx`**
- Props: `session: Session`
- Show tool badge (colored), title, project path, message count, relative date
- Click → navigate to `/sessions/{id}`

**`MessageViewer.tsx`**
- Props: `messages: Message[]`
- Alternate bubble layout: user on right, assistant on left
- `react-markdown` for content, `rehype-highlight` for code blocks

**`SearchResult.tsx`**
- Props: `result: SearchResult`
- Show score bar, snippet with query terms bolded, tool badge, project, link to session

---

## 11. Configuration

`~/.coding-sessions/config.toml` (created on first `sess index`):

```toml
[embedding]
provider = "openai"           # "openai" | "local"
model = "text-embedding-3-small"
batch_size = 100
# openai_api_key = "sk-..."   # optional; omit to use local embeddings only

[sources]
claude = true
codex = true
cursor = true

[server]
port = 8000
host = "127.0.0.1"
```

Read with `tomllib` (stdlib in Python 3.11+). Do not use repo-root `.env` files; secrets stay under `~/.coding-sessions/` only.

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
13. `desktop/` — Tauri + React (scaffold → pages → components)

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
