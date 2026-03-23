# coding-session-explorer

> Browse, search, and visualize every AI coding session — Claude Code, Codex CLI, and Cursor — in one place.

No more `codex --sessions` or `cursor --resume` hunting. Every conversation is indexed locally, semantically searchable, and available via CLI and an optional OpenTUI terminal UI.

## Features

- **Unified index** — parses sessions from Claude Code, Codex CLI, and Cursor automatically
- **Semantic search** — `sess search "how did I fix that auth bug"` finds the exact session
- **CLI-first** — Rich-rendered tables, conversation viewer, ASCII heatmap, all in terminal
- **OpenTUI app** — type **`sess`** (no subcommand) or **`sess resume`** / **`sess tui`** to reopen the browser (Bun + `@opentui/core`); list view supports **agent / project / days** filters (same semantics as `sess list --tool --project --days`)
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

# (Optional) OpenTUI — install deps once, then reopen anytime with:
cd tui && bun install && cd ..
sess              # same as sess tui / sess resume
```

Tip: add `alias cse=sess` (or `alias cse='uv run sess'` in the repo) so one short command brings the UI back.

## CLI Usage

```bash
sess index                        # index new/changed sources only
sess reindex                      # force full reindex (same as sess index --force)
sess list                         # list all sessions (Rich table)
sess list --tool claude --days 7  # filter by tool / recency
sess view <session-id>            # render conversation in terminal
sess search "query"               # semantic search across sessions
sess stats                        # ASCII contribution heatmap
sess watch                        # background file watcher
sess serve                        # start FastAPI only (e.g. for `sess tui --no-serve` workflows)
sess                              # OpenTUI (default — same as sess tui / sess resume)
sess resume                       # explicit alias for the TUI
sess tui                          # same; supports --port / --no-serve
```

## Current Verification Status

- ✅ `pytest tests/test_crawlers.py`
- ✅ `pytest tests/test_indexing_and_search.py`
- ✅ `pytest tests`
- ✅ `pyproject.toml` now uses `setuptools.build_meta`, allowing `uv sync --extra dev` and `uv run` verification flows.
- ✅ `ruff check core cli server tests` clean (after auto-format/import/order fixes)
- ✅ `pyright` clean when run via `uv run pyright` with `uv sync --extra dev` environment
- ✅ Manual `indexer` and crawler regression scenario now passes with isolated HOME fixture data and does not double-count stale sessions.
- ✅ `tui/` typechecks with `bun run typecheck` after `bun install`.

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
 Typer + Rich          JSON API
                              ↓
                       tui/ OpenTUI (Bun)
```

## Stack

- **Core / CLI**: Python 3.12, Typer, Rich, SQLModel, ChromaDB, watchdog
- **Embeddings**: OpenAI `text-embedding-3-small` (swap in `sentence-transformers` for fully offline)
- **Server**: FastAPI + Uvicorn
- **TUI**: Bun + [@opentui/core](https://opentui.com/) (Zig-backed terminal UI)

## Contributing

See [AGENTS.md](./AGENTS.md) for the full implementation spec (designed for AI coding agents).
