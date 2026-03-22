# coding-session-explorer

> Browse, search, and visualize every AI coding session — Claude Code, Codex CLI, and Cursor — in one place.

No more `codex --sessions` or `cursor --resume` hunting. Every conversation is indexed locally, semantically searchable, and available via CLI or a native desktop app.

## Features

- **Unified index** — parses sessions from Claude Code, Codex CLI, and Cursor automatically
- **Semantic search** — `sess search "how did I fix that auth bug"` finds the exact session
- **CLI-first** — Rich-rendered tables, conversation viewer, ASCII heatmap, all in terminal
- **Desktop app** — Tauri (native macOS/Windows/Linux) with timeline, heatmap, and full-text viewer
- **Live indexing** — `sess watch` monitors source directories and indexes new sessions in real time
- **Project-aware** — sessions grouped by repo path, cross-tool

## Data Sources

| Tool | Location | Format |
|---|---|---|
| Claude Code | `~/.claude/transcripts/` + `~/.claude/projects/` | JSONL |
| Codex CLI | `~/.codex/sessions/YYYY/MM/DD/` | JSONL |
| Cursor | `~/.cursor/chats/**/store.db` | SQLite |

All indexed data is stored locally in `~/.coding-sessions/`.

## Install

```bash
# Clone
git clone https://github.com/jiatastic/coding-session-explorer
cd coding-session-explorer

# Install Python CLI + core
pip install -e ".[dev]"

# Run initial index
sess index

# (Optional) Start the desktop app
cd desktop && cargo tauri dev
```

## CLI Usage

```bash
sess index                        # full reindex from all sources
sess list                         # list all sessions (Rich table)
sess list --tool claude --days 7  # filter by tool / recency
sess view <session-id>            # render conversation in terminal
sess search "query"               # semantic search across sessions
sess stats                        # ASCII contribution heatmap
sess watch                        # background file watcher
sess serve                        # start FastAPI server (used by desktop app)
```

## Architecture

```
~/.claude/   ~/.codex/   ~/.cursor/
      ↓            ↓           ↓
   core/crawlers (Python parsers)
              ↓
   ~/.coding-sessions/
     sessions.db   ← SQLite (metadata + messages)
     chroma/       ← ChromaDB (vector embeddings)
        ↙                    ↘
 CLI (sess)            server/ FastAPI
 Typer + Rich          (Tauri sidecar)
                              ↓
                       desktop/ Tauri
                       React + shadcn/ui
```

## Stack

- **Core / CLI**: Python 3.12, Typer, Rich, SQLModel, ChromaDB, watchdog
- **Embeddings**: OpenAI `text-embedding-3-small` (swap in `sentence-transformers` for fully offline)
- **Server**: FastAPI + Uvicorn
- **Desktop**: Tauri v2 (Rust) + React 18 + Tailwind CSS + shadcn/ui

## Contributing

See [AGENTS.md](./AGENTS.md) for the full implementation spec (designed for AI coding agents).
