# Plan: User distribution (brew / curl / npm)

## Problem

Today, install docs assume **cloning the repo** and using **`uv` or `pip`** from the project root. That fits contributors, not typical end users who expect **`brew install`**, **`curl | bash`**, or **`npm install -g`**.

## Goals

- One-line install for macOS (primary) and documented paths for Linux.
- Installed **`sess`** on `PATH` without manual venv management.
- **TUI** remains optional: either document **Bun + `tui/bun install`** or bundle a documented fallback.
- **No breaking change** to existing `pip install -e .` / `uv sync` workflows.

## Non-goals (initially)

- Publishing the Python package to PyPI (can follow after brew works).
- Windows installer (MSI); document manual steps only unless demand is clear.
- Rewriting the core in Node; **npm** is at most a thin wrapper.

---

## Phase 1 — Publishable Python artifact

1. **Versioning**
   - Ensure `pyproject.toml` version is bumped per release.
   - Tag releases in Git (`v0.x.y`).

2. **PyPI (optional but recommended)**
   - `python -m build` + `twine upload` (or CI on tag).
   - Users could then: `pipx install coding-session-explorer` (good story even before brew).

3. **Entry point**
   - Keep `[project.scripts] sess = "cli.main:app"` as the single CLI entry.

**Exit criteria:** `pipx install coding-session-explorer` (or `pip install`) from PyPI works on a clean machine.

---

## Phase 2 — Homebrew (macOS)

1. **Tap or core**
   - Prefer a **custom tap** (`brew install org/tap/coding-session-explorer`) for fast iteration; consider **homebrew-core** later.

2. **Formula sketch**
   - `depends_on "python@3.12"` (or `python@3.13` when supported).
   - Install with `pip install` / `python -m pip install .` into a **virtualenv inside the Cellar** (standard Homebrew Python app pattern) **or** depend on `pipx` and run `pipx install`.
   - Install **`sess`** binary that invokes the venv’s `sess`.

3. **Post-install notes**
   - **Caveat:** Chroma / sentence-transformers / first index may download large artifacts — document in `caveats` block.
   - **TUI:** print caveat that **Bun** is required and user should run `sess tui` once to see install hint, or ship a **`brew install bun`** recommendation.

4. **CI**
   - `brew test` bot or GitHub Action: `brew install ./Formula/... && sess --help`.

**Exit criteria:** Fresh Mac user can `brew install …` and run `sess index`.

---

## Phase 3 — curl installer

1. **`install.sh` (hosted on release assets or raw GitHub URL)**
   - Detect OS (macOS / Linux); refuse or warn on Windows.
   - Prefer **pipx** if present: `pipx install coding-session-explorer==$VERSION`.
   - Else: create **`~/.local/share/coding-session-explorer/venv`**, `python -m venv`, `pip install`, symlink **`sess`** into **`~/.local/bin`** (or append PATH instructions).
   - Idempotent: re-run upgrades venv.

2. **Documentation**
   - README one-liner: `curl -fsSL https://…/install.sh | bash`
   - Checksum / signed releases (optional hardening).

**Exit criteria:** Script works on clean macOS and Ubuntu LTS without manual clone.

---

## Phase 4 — npm (optional shim)

1. **Package scope**
   - e.g. `@org/coding-session-explorer-cli` with a **single `bin`** file.

2. **Behavior**
   - **Preferred:** spawn **`sess`** if on PATH; if missing, print install link (brew/curl/pipx).
   - **Avoid:** bundling full Python stack inside npm unless explicitly scoped as experimental.

3. **TUI**
   - Optional second bin `coding-session-explorer-tui` that runs `bun run …` if repo/tui present — usually **not** worth it for global npm users; prefer documenting **`sess tui`** after brew install.

**Exit criteria:** `npx @org/coding-session-explorer-cli -- --help` fails gracefully with install instructions if `sess` missing.

---

## Phase 5 — README and release process

1. Replace contributor-first flow with **“Install”** section: brew → curl → pipx → clone.
2. **CHANGELOG** + GitHub Releases with assets (`install.sh`, checksums).
3. **Version sync** between formula, install script, and PyPI.

---

## Open questions

- **Bun as a hard dependency for TUI:** require via brew formula (`depends_on "bun"`) vs optional vs vendored — decide per binary size and policy.
- **Code signing / notarization:** only if shipping a `.pkg` or `.app`; out of scope for formula-only.
- **Linux brew vs apt:** curl + pipx may be enough for Linux; separate `.deb` is another project.

---

## Suggested order of implementation

1. PyPI + pipx story  
2. Homebrew tap + formula  
3. `install.sh`  
4. npm shim (low priority)  
5. README + release checklist
