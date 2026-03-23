# Plan: Background indexing (“always save sessions”)

## Problem

`sess index` is manual. **`sess watch`** already reacts to filesystem changes under Claude / Codex / Cursor data dirs, but nothing starts it at login, so it does not feel like a **plugin that always saves**.

## Goals

- **Login / boot:** indexing watcher runs without opening a terminal every day.
- **Observable:** user can tell if watch is running (pid file, `sess doctor`, or logs).
- **Robust:** transient parse errors do not kill the long-running process; optional debounce for noisy editors.

## Non-goals (initially)

- IDE extensions (Cursor/VS Code) — separate plan if needed.
- Remote or cloud sync of the index.

---

## Phase 1 — CLI hardening (`sess watch`)

1. **`--log-file PATH`**
   - Append logs with rotation optional later; default remains stderr/stdout for interactive use.

2. **`--pid-file PATH`**
   - Write PID on start; remove on clean exit; stale-file detection (PID not alive → overwrite).

3. **Signal handling**
   - Document SIGTERM/SIGINT cleanup (remove pid file, flush logs).

4. **Debounce (if needed)**
   - Coalesce multiple writes to the same source path within **N ms** (e.g. 300–500) before `parse` + `upsert`.

5. **Error loop**
   - On parse failure: log exception, **continue**; optional exponential backoff per path to avoid log floods.

**Exit criteria:** `sess watch --log-file ~/Library/Logs/... --pid-file ~/.../sess-watch.pid` runs stably for 24h under normal coding.

---

## Phase 2 — macOS LaunchAgent

1. **Template plist** under `contrib/launchd/`
   - `WorkingDirectory` optional.
   - `ProgramArguments`: full path to **`sess`** or **`uv run sess`** — **prefer absolute path to venv `sess`** after brew/pipx install.
   - `RunAtLoad` true, `KeepAlive` false (or true if we want respawn — decide; `KeepAlive` true is common for watchers).
   - `StandardOutPath` / `StandardErrorPath` for logs.

2. **Typer commands (optional but UX-friendly)**
   - `sess install-watch` — copy plist to `~/Library/LaunchAgents/`, `launchctl bootstrap gui/$UID`.
   - `sess uninstall-watch` — `bootout`, remove plist.

3. **PATH issues**
   - LaunchAgents often lack full PATH; plist should use **absolute paths** to `sess` and Python if needed, or a small **wrapper script** installed next to `sess`.

**Exit criteria:** New Mac user runs `sess install-watch` once; after reboot, watch is running and index updates when a new session file appears.

---

## Phase 3 — Linux systemd (user unit)

1. **Unit file** under `contrib/systemd/`  
   - `Type=simple`, `ExecStart=/full/path/to/sess watch --log-file … --pid-file …`  
   - `Restart=on-failure` with `RestartSec=5`.

2. **Install helper**
   - `sess install-watch` detects Linux, installs to `~/.config/systemd/user/`, runs `systemctl --user daemon-reload && enable --now`.

**Exit criteria:** Same as macOS, on Ubuntu/Fedora with systemd user session.

---

## Phase 4 — `sess doctor`

1. Print:
   - Config / DB / Chroma paths (from existing `core.config` / `db`).
   - **Watch:** pid file present + process alive?
   - Last index modification heuristic (e.g. `sessions.db` mtime or a small `meta` table row if added later).

**Exit criteria:** One command answers “is background indexing on?”

---

## Phase 5 — Documentation

1. README section **“Always-on indexing”** with macOS + Linux instructions.
2. Windows: **Task Scheduler** steps only (no automation in v1).

---

## Open questions

- **KeepAlive:** `true` vs `false` for LaunchAgent — prefer **true** for reliability, accept slightly more restarts on crash loops (mitigate with backoff in Python).
- **Multiple users / multiple Python installs:** brew vs pipx path in plist — `install-watch` should **resolve `shutil.which("sess")`** at install time and bake into plist, or generate wrapper script.

---

## Suggested order of implementation

1. `sess watch` flags + error/debounce behavior  
2. `contrib/launchd` + `sess install-watch` (macOS)  
3. `contrib/systemd` + Linux branch in `install-watch`  
4. `sess doctor`  
5. README
