/**
 * OpenTUI front-end for coding-session-explorer.
 * Expects FastAPI at SESS_API_BASE (default http://127.0.0.1:8000).
 */
import {
  Box,
  Input,
  InputRenderableEvents,
  ScrollBox,
  Select,
  SelectRenderableEvents,
  Text,
  createCliRenderer,
  type CliRenderer,
} from "@opentui/core"

type ApiMessage = {
  id: string
  role: string
  content: string
  timestamp?: string | null
}

type ApiSession = {
  id: string
  source: string
  title: string
  message_count: number
  project_path?: string | null
  repo_url?: string | null
  summary?: string | null
  updated_at?: string
  messages?: ApiMessage[]
}

type ApiSearchHit = {
  session_id: string
  session_title: string
  source: string
  project_path?: string | null
  snippet: string
  score: number
}

/** Mirrors GET /sessions query filters (tool + project path substring + max age in days). */
type ListFilters = {
  tool: string
  project: string
  days: string
}

type ListScreenState = ListFilters & { search: string }

const EMPTY_FILTERS: ListFilters = { tool: "", project: "", days: "" }

const EMPTY_LIST_STATE: ListScreenState = { ...EMPTY_FILTERS, search: "" }

function normalizeTool(raw: string): string {
  const t = raw.trim().toLowerCase()
  return t === "claude" || t === "codex" || t === "cursor" ? t : ""
}

function buildSessionsQuery(limit: number, f: ListFilters): string {
  const p = new URLSearchParams()
  p.set("limit", String(limit))
  const tool = normalizeTool(f.tool)
  if (tool) p.set("tool", tool)
  const proj = f.project.trim()
  if (proj) p.set("project", proj)
  const d = f.days.trim()
  if (d && /^\d+$/.test(d)) p.set("days", d)
  return p.toString()
}

function filterSearchHits(hits: ApiSearchHit[], f: ListFilters): ApiSearchHit[] {
  const tool = normalizeTool(f.tool)
  let out = hits
  if (tool) out = out.filter((h) => h.source === tool)
  const sub = f.project.trim().toLowerCase()
  if (sub) {
    out = out.filter((h) => {
      const path = (h.project_path ?? "").toLowerCase()
      return path.includes(sub)
    })
  }
  return out
}

type IndexStatus = {
  running: boolean
  phase: string
  crawler: string | null
  current: number
  total: number
  detail: string | null
  stats: Record<string, number> | null
  error: string | null
}

/** Select first row — triggers POST /index + progress polling */
const REINDEX_VALUE = "__reindex__"

const apiBase = () => process.env.SESS_API_BASE?.replace(/\/$/, "") ?? "http://127.0.0.1:8000"

async function apiHealth(base: string): Promise<boolean> {
  try {
    const r = await fetch(`${base}/health`, { signal: AbortSignal.timeout(5000) })
    return r.ok
  } catch {
    return false
  }
}

async function apiSessions(base: string, limit: number, filters: ListFilters = EMPTY_FILTERS): Promise<ApiSession[]> {
  const qs = buildSessionsQuery(limit, filters)
  const r = await fetch(`${base}/sessions?${qs}`, { signal: AbortSignal.timeout(60_000) })
  if (!r.ok) throw new Error(`sessions: HTTP ${r.status}`)
  return r.json() as Promise<ApiSession[]>
}

async function apiSession(base: string, id: string): Promise<ApiSession> {
  const r = await fetch(`${base}/sessions/${encodeURIComponent(id)}`, { signal: AbortSignal.timeout(60_000) })
  if (!r.ok) throw new Error(`session: HTTP ${r.status}`)
  return r.json() as Promise<ApiSession>
}

type ResumeSpec = { argv: string[]; cwd: string | null; hint?: string }

async function apiResume(base: string, id: string): Promise<ResumeSpec> {
  const r = await fetch(`${base}/sessions/${encodeURIComponent(id)}/resume`, { signal: AbortSignal.timeout(10_000) })
  if (!r.ok) throw new Error(`resume: HTTP ${r.status}`)
  return r.json() as Promise<ResumeSpec>
}

async function runResumeInNative(renderer: CliRenderer, base: string, sessionId: string) {
  let spec: ResumeSpec
  try {
    spec = await apiResume(base, sessionId)
  } catch (e) {
    console.error(e instanceof Error ? e.message : String(e))
    return
  }
  const hint = (spec.hint ?? "").trim()
  if (hint) console.error(hint)
  renderer.destroy()
  const res = Bun.spawnSync(spec.argv, {
    cwd: spec.cwd ?? undefined,
    stdio: ["inherit", "inherit", "inherit"],
    env: process.env,
  })
  process.exit(typeof res.exitCode === "number" ? res.exitCode : 1)
}

async function apiSearch(base: string, q: string, limit: number): Promise<ApiSearchHit[]> {
  const url = `${base}/search?q=${encodeURIComponent(q)}&limit=${limit}&mode=auto`
  const r = await fetch(url, { signal: AbortSignal.timeout(120_000) })
  if (!r.ok) throw new Error(`search: HTTP ${r.status}`)
  return r.json() as Promise<ApiSearchHit[]>
}

async function apiIndexStatus(base: string): Promise<IndexStatus> {
  const r = await fetch(`${base}/index/status`, { signal: AbortSignal.timeout(10_000) })
  if (!r.ok) throw new Error(`index/status: HTTP ${r.status}`)
  return r.json() as Promise<IndexStatus>
}

type OpenAIKeyStatus = {
  configured: boolean
  source: "env" | "file" | "none"
  has_stored_key: boolean
}

async function apiOpenAIGet(base: string): Promise<OpenAIKeyStatus> {
  const r = await fetch(`${base}/settings/openai`, { signal: AbortSignal.timeout(10_000) })
  if (!r.ok) throw new Error(`settings/openai: HTTP ${r.status}`)
  return r.json() as Promise<OpenAIKeyStatus>
}

async function apiOpenAIPut(base: string, apiKey: string): Promise<OpenAIKeyStatus> {
  const r = await fetch(`${base}/settings/openai`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey }),
    signal: AbortSignal.timeout(15_000),
  })
  if (!r.ok) throw new Error(`settings/openai PUT: HTTP ${r.status}`)
  return r.json() as Promise<OpenAIKeyStatus>
}

function describeOpenAIStatus(st: OpenAIKeyStatus): string {
  if (st.source === "env") {
    let s = "OpenAI: active — OPENAI_API_KEY in environment (overrides file)."
    if (st.has_stored_key) s += " (A key is also saved on disk.)"
    return s
  }
  if (st.source === "file") return "OpenAI: active — key in ~/.coding-sessions/secrets.json"
  return "OpenAI: not set — embeddings use local sentence-transformers."
}

function clearRoot(renderer: CliRenderer) {
  const root = renderer.root
  const kids = [...root.getChildren()]
  for (const k of kids) {
    root.remove(k.id)
  }
}

function truncate(s: string, max: number): string {
  const t = s.replace(/\s+/g, " ").trim()
  return t.length <= max ? t : `${t.slice(0, max - 1)}…`
}

function shortenPath(path: string, max: number): string {
  const norm = path.replace(/\\/g, "/")
  return truncate(norm, max)
}

function sessionListDescription(s: ApiSession): string {
  const meta = `${s.source} · ${s.message_count} msgs · ${s.id.slice(0, 10)}…`
  const sum = (s.summary ?? "").trim()
  if (sum) return `${truncate(sum, 76)} · ${meta}`
  return meta
}

function sessionOptions(sessions: ApiSession[]) {
  return sessions.map((s) => ({
    name: truncate(s.title || "(no title)", 72),
    description: sessionListDescription(s),
    value: s.id,
  }))
}

function listSelectOptions(sessions: ApiSession[]) {
  return [
    {
      name: "▶ Full reindex (force)…",
      description: "Live progress · embeddings may take a while",
      value: REINDEX_VALUE,
    },
    ...sessionOptions(sessions),
  ]
}

function searchOptions(hits: ApiSearchHit[]) {
  return hits.map((h) => ({
    name: truncate(h.session_title || "(no title)", 72),
    description: `${h.source} · score ${h.score.toFixed(3)} · ${truncate(h.snippet, 100)}`,
    value: h.session_id,
  }))
}

function indexStatusLines(s: IndexStatus, maxW: number): string[] {
  if (s.phase === "error")
    return [`Error: ${s.error ?? "unknown"}`, "Check terminal running `sess serve` for trace."]
  if (s.phase === "done" && s.stats) {
    return [
      "Done.",
      `Updated: ${s.stats.new_sessions} sessions, ${s.stats.new_messages} messages, skipped ${s.stats.skipped}`,
    ]
  }
  if (s.running || s.phase === "running") {
    if (s.detail === "no files") {
      return [`${s.crawler ?? "?"}: no source files found (skipped)`]
    }
    if (!s.total) {
      const c = s.crawler ? ` (${s.crawler})` : ""
      return [`Starting crawl${c}…`]
    }
    const pct = Math.round((100 * s.current) / s.total)
    const line1 = `${s.crawler ?? "?"}  ${s.current} / ${s.total}  (${pct}%)`
    const line2 = s.detail ? shortenPath(s.detail, maxW) : ""
    return line2 ? [line1, line2] : [line1]
  }
  return ["Waiting…"]
}

/** Inner bar width (characters between `[` and `]`). */
function progressBarInnerWidth(maxW: number): number {
  return Math.max(10, Math.min(42, maxW - 12))
}

function buildDeterminateBar(width: number, pct: number): string {
  const p = Math.max(0, Math.min(100, pct))
  const filled = width > 0 ? Math.min(width, Math.round((p / 100) * width)) : 0
  const bar = "█".repeat(filled) + "░".repeat(Math.max(0, width - filled))
  return `[${bar}] ${p}%`
}

/** Sliding segment while total is unknown or waiting on the server. */
function buildIndeterminateBar(width: number, tick: number): string {
  const seg = Math.max(3, Math.floor(width * 0.34))
  const maxStart = Math.max(0, width - seg)
  const span = maxStart + 1 || 1
  const start = tick % span
  let out = ""
  for (let i = 0; i < width; i++) {
    out += i >= start && i < start + seg ? "█" : "░"
  }
  return `[${out}]`
}

function indexProgressBarLine(s: IndexStatus, maxW: number, animTick: number): string | null {
  if (s.phase === "error") return null
  if (s.phase === "done" && s.stats) return null

  const inner = progressBarInnerWidth(maxW)
  const active = s.running || s.phase === "running"
  const waiting = !active && s.phase !== "error"

  if (active && s.detail === "no files") {
    return `${buildIndeterminateBar(inner, animTick)}  (no files)`
  }
  if (active && s.total > 0) {
    const pct = Math.round((100 * s.current) / s.total)
    return buildDeterminateBar(inner, pct)
  }
  if (active || waiting) {
    return buildIndeterminateBar(inner, animTick)
  }
  return null
}

async function showIndexingScreen(
  renderer: CliRenderer,
  base: string,
  onComplete: () => Promise<void>,
) {
  uiMode = "indexing"
  openSettings = null
  settingsBack = null
  detailSessionId = null
  const maxW = Math.max(24, renderer.width - 4)

  const initial: IndexStatus = {
    running: true,
    phase: "running",
    crawler: null,
    current: 0,
    total: 0,
    detail: null,
    stats: null,
    error: null,
  }

  let latest = initial
  let animTick = 0

  const renderIndexingFrame = () => {
    clearRoot(renderer)
    const bar = indexProgressBarLine(latest, maxW, animTick)
    const lines = indexStatusLines(latest, maxW)
    renderer.root.add(
      Box(
        {
          id: "index-shell",
          width: "100%",
          height: "100%",
          flexDirection: "column",
          padding: 1,
          gap: 1,
          backgroundColor: "#16161e",
        },
        Text({ content: "Indexing…", fg: "#bb9af7" }),
        ...(bar ? [Text({ content: bar, fg: "#7aa2f7" })] : []),
        ...lines.map((ln) => Text({ content: ln, fg: "#c0caf5" })),
        Text({
          content: "TUI polls GET /index/status · Ctrl+C exits the TUI only",
          fg: "#565f89",
        }),
      ),
    )
  }

  const setIndexStatus = (s: IndexStatus) => {
    latest = s
    renderIndexingFrame()
  }

  animTick = 0
  renderIndexingFrame()
  const animId = setInterval(() => {
    animTick += 1
    renderIndexingFrame()
  }, 110)

  const stopAnim = () => clearInterval(animId)

  try {
    try {
      const post = await fetch(`${base}/index`, { method: "POST", signal: AbortSignal.timeout(30_000) })
      if (!post.ok && post.status !== 409) {
        throw new Error(`POST /index → HTTP ${post.status}`)
      }
    } catch (e) {
      stopAnim()
      setIndexStatus({
        running: false,
        phase: "error",
        crawler: null,
        current: 0,
        total: 0,
        detail: null,
        stats: null,
        error: e instanceof Error ? e.message : String(e),
      })
      await new Promise((r) => setTimeout(r, 2500))
      await onComplete()
      return
    }

    for (;;) {
      let s: IndexStatus
      try {
        s = await apiIndexStatus(base)
      } catch (e) {
        stopAnim()
        setIndexStatus({
          running: false,
          phase: "error",
          crawler: null,
          current: 0,
          total: 0,
          detail: null,
          stats: null,
          error: e instanceof Error ? e.message : String(e),
        })
        await new Promise((r) => setTimeout(r, 2500))
        break
      }
      setIndexStatus(s)
      if (s.phase === "error" || (s.phase === "done" && !s.running)) break
      if (!s.running && s.phase === "idle") break
      await new Promise((r) => setTimeout(r, 400))
    }

    stopAnim()
    renderIndexingFrame()
    await new Promise((r) => setTimeout(r, 500))
    await onComplete()
  } catch (err) {
    stopAnim()
    throw err
  }
}

let uiMode: "list" | "detail" | "empty" | "indexing" | "settings" = "list"
let navigateBack: (() => Promise<void>) | null = null
let emptyIndexResume: (() => Promise<void>) | null = null
/** List/empty: press `s` to open OpenAI settings. */
let openSettings: (() => void) | null = null
/** Settings: `b` runs this to return to the previous screen. */
let settingsBack: (() => Promise<void>) | null = null
/** Set while session detail is visible; used for `o` → native CLI handoff. */
let detailSessionId: string | null = null

/** OpenTUI Text `content` setter is typed as StyledText; plain strings work at runtime. */
function setPlainText(line: { content: unknown }, s: string) {
  line.content = s
}

async function showOpenAISettings(renderer: CliRenderer, base: string, onBack: () => Promise<void>) {
  uiMode = "settings"
  openSettings = null
  settingsBack = onBack
  detailSessionId = null
  clearRoot(renderer)

  const statusLine = Text({ content: "Loading…", fg: "#a9b1d6", wrapMode: "word" })
  const toastLine = Text({ content: "", fg: "#9ece6a" })
  const keyInput = Input({
    id: "openai-key-input",
    width: "100%",
    placeholder: "Paste sk-… here (shown in plain text in terminal)",
    maxLength: 512,
  })

  const refreshStatus = async () => {
    try {
      const st = await apiOpenAIGet(base)
      setPlainText(statusLine, describeOpenAIStatus(st))
    } catch (e) {
      setPlainText(statusLine, e instanceof Error ? e.message : String(e))
    }
  }

  await refreshStatus()

  const select = Select({
    id: "openai-settings-select",
    width: "100%",
    flexGrow: 1,
    minHeight: 5,
    showDescription: true,
    options: [
      {
        name: "Save key (from field above)",
        description: "Writes ~/.coding-sessions/secrets.json (file mode 0600)",
        value: "save",
      },
      {
        name: "Clear saved key",
        description: "Removes file only; shell OPENAI_API_KEY unchanged",
        value: "clear",
      },
      { name: "Back", description: "", value: "back" },
    ],
    backgroundColor: "#1a1b26",
    selectedBackgroundColor: "#33467c",
    textColor: "#c0caf5",
  })

  select.on(SelectRenderableEvents.ITEM_SELECTED, async (_i, opt) => {
    const v = opt.value as string
    setPlainText(toastLine, "")
    if (v === "back") {
      settingsBack = null
      await onBack()
      return
    }
    if (v === "clear") {
      try {
        await apiOpenAIPut(base, "")
        setPlainText(toastLine, "Cleared saved key.")
        await refreshStatus()
      } catch (e) {
        setPlainText(toastLine, e instanceof Error ? e.message : String(e))
      }
      return
    }
    if (v === "save") {
      const raw = keyInput.value.trim()
      if (!raw) {
        setPlainText(toastLine, "Paste a key in the field above first.")
        return
      }
      try {
        await apiOpenAIPut(base, raw)
        keyInput.value = ""
        setPlainText(toastLine, "Saved.")
        await refreshStatus()
      } catch (e) {
        setPlainText(toastLine, e instanceof Error ? e.message : String(e))
      }
    }
  })

  const shell = Box(
    {
      id: "settings-shell",
      width: "100%",
      height: "100%",
      flexDirection: "column",
      padding: 1,
      gap: 1,
      backgroundColor: "#16161e",
    },
    Text({ content: "OpenAI API key — s from list · b back · Ctrl+C quit", fg: "#bb9af7" }),
    statusLine,
    toastLine,
    Text({ content: "New key (optional):", fg: "#565f89" }),
    keyInput,
    select,
  )

  renderer.root.add(shell)
  select.focus()
}

async function showSessionDetail(renderer: CliRenderer, base: string, session: ApiSession) {
  uiMode = "detail"
  openSettings = null
  settingsBack = null
  detailSessionId = session.id
  clearRoot(renderer)

  const lines: string[] = [
    `${session.title}`,
    `${session.source} · ${session.message_count} messages · ${session.id}`,
    session.project_path ? `Project: ${session.project_path}` : "",
  ].filter(Boolean)

  const blocks: ReturnType<typeof Box>[] = []
  for (const line of lines) {
    blocks.push(Box({ paddingY: 0 }, Text({ content: line, fg: "#a9b1d6" })))
  }

  const sum = (session.summary ?? "").trim()
  if (sum) {
    blocks.push(
      Box(
        {
          padding: 1,
          marginTop: 1,
          backgroundColor: "#2a2e3f",
          border: true,
          borderStyle: "rounded",
          borderColor: "#565f89",
        },
        Text({ content: "AI summary", fg: "#bb9af7" }),
        Text({ content: sum, fg: "#c0caf5" }),
      ),
    )
  }

  blocks.push(Box({ paddingY: 0, marginTop: 1 }, Text({ content: "—", fg: "#565f89" })))

  const msgs = session.messages ?? []
  for (const m of msgs) {
    const head = `[${m.role}]${m.timestamp ? " " + m.timestamp : ""}`
    const body = m.content || ""
    blocks.push(
      Box(
        { padding: 1, marginTop: 1, backgroundColor: "#24283b" },
        Text({ content: head, fg: "#7aa2f7" }),
        Text({ content: body || "(empty)", fg: "#c0caf5" }),
      ),
    )
  }

  const scroll = ScrollBox(
    {
      id: "detail-scroll",
      width: "100%",
      flexGrow: 1,
      minHeight: 5,
      scrollY: true,
      rootOptions: { backgroundColor: "#1a1b26" },
    },
    ...blocks,
  )

  const shell = Box(
    {
      id: "detail-shell",
      width: "100%",
      height: "100%",
      flexDirection: "column",
      padding: 1,
      gap: 1,
      backgroundColor: "#16161e",
    },
    Text({ content: "Session — o native tool · b back · Ctrl+C quit", fg: "#bb9af7" }),
    scroll,
  )

  renderer.root.add(shell)
  scroll.focus()
}

type TextField = { value: string }

function filtersFromInputs(toolIn: TextField, projectIn: TextField, daysIn: TextField): ListFilters {
  return {
    tool: toolIn.value,
    project: projectIn.value,
    days: daysIn.value,
  }
}

function listStateFromInputs(
  toolIn: TextField,
  projectIn: TextField,
  daysIn: TextField,
  searchIn: TextField,
): ListScreenState {
  return {
    ...filtersFromInputs(toolIn, projectIn, daysIn),
    search: searchIn.value,
  }
}

async function showListScreen(
  renderer: CliRenderer,
  base: string,
  initialSessions: ApiSession[],
  state: ListScreenState = EMPTY_LIST_STATE,
) {
  uiMode = "list"
  settingsBack = null
  openSettings = null
  detailSessionId = null
  clearRoot(renderer)

  const searchInput = Input({
    id: "search-input",
    width: "100%",
    value: state.search,
    placeholder: "Semantic search — Enter. Clear + Enter restores filtered list.",
    maxLength: 500,
  })

  const toolInput = Input({
    id: "filter-tool",
    flexGrow: 1,
    flexShrink: 0,
    minWidth: 10,
    maxWidth: 14,
    value: state.tool,
    placeholder: "tool: all",
    maxLength: 12,
  })

  const projectInput = Input({
    id: "filter-project",
    flexGrow: 3,
    minWidth: 12,
    value: state.project,
    placeholder: "project path contains…",
    maxLength: 240,
  })

  const daysInput = Input({
    id: "filter-days",
    flexGrow: 0,
    flexShrink: 0,
    minWidth: 6,
    maxWidth: 8,
    value: state.days,
    placeholder: "days",
    maxLength: 5,
  })

  const select = Select({
    id: "session-select",
    width: "100%",
    flexGrow: 1,
    minHeight: 8,
    showDescription: true,
    showScrollIndicator: true,
    options: listSelectOptions(initialSessions),
    backgroundColor: "#1a1b26",
    selectedBackgroundColor: "#33467c",
    textColor: "#c0caf5",
  })

  const runSearch = async (raw: string) => {
    const q = raw.trim()
    const f = filtersFromInputs(toolInput, projectInput, daysInput)
    if (!q) {
      try {
        const rows = await apiSessions(base, 400, f)
        select.options = listSelectOptions(rows)
        select.setSelectedIndex(0)
      } catch (e) {
        select.options = [
          {
            name: "(list failed)",
            description: e instanceof Error ? e.message : String(e),
            value: "",
          },
        ]
        select.setSelectedIndex(0)
      }
      return
    }
    try {
      const hits = await apiSearch(base, q, 40)
      const filtered = filterSearchHits(hits, f)
      select.options = filtered.length
        ? searchOptions(filtered)
        : [{ name: "(no results)", description: "Try another query or filters", value: "" }]
      select.setSelectedIndex(0)
    } catch (e) {
      select.options = [
        {
          name: "(search failed)",
          description: e instanceof Error ? e.message : String(e),
          value: "",
        },
      ]
      select.setSelectedIndex(0)
    }
  }

  const applyFilters = () => {
    void runSearch(searchInput.value)
  }

  searchInput.on(InputRenderableEvents.ENTER, () => {
    void runSearch(searchInput.value)
  })

  for (const inp of [toolInput, projectInput, daysInput]) {
    inp.on(InputRenderableEvents.ENTER, () => {
      applyFilters()
    })
  }

  select.on(SelectRenderableEvents.ITEM_SELECTED, async (_i, opt) => {
    const id = opt.value as string
    if (id === REINDEX_VALUE) {
      const saved = listStateFromInputs(toolInput, projectInput, daysInput, searchInput)
      await showIndexingScreen(renderer, base, async () => {
        try {
          const f: ListFilters = {
            tool: saved.tool,
            project: saved.project,
            days: saved.days,
          }
          const next = await apiSessions(base, 400, f)
          if (next.length === 0) showEmptyScreen(renderer, base)
          else await showListScreen(renderer, base, next, saved)
        } catch {
          await showListScreen(renderer, base, initialSessions, saved)
        }
      })
      return
    }
    if (!id) return
    const frozen = listStateFromInputs(toolInput, projectInput, daysInput, searchInput)
    navigateBack = async () => {
      try {
        const f: ListFilters = {
          tool: frozen.tool,
          project: frozen.project,
          days: frozen.days,
        }
        const s = await apiSessions(base, 400, f)
        await showListScreen(renderer, base, s, frozen)
      } catch {
        await showListScreen(renderer, base, initialSessions, frozen)
      }
    }
    try {
      const full = await apiSession(base, id)
      await showSessionDetail(renderer, base, full)
    } catch (e) {
      select.options = [
        {
          name: "(load failed)",
          description: e instanceof Error ? e.message : String(e),
          value: "",
        },
      ]
      select.setSelectedIndex(0)
    }
  })

  const filterRow = Box(
    {
      id: "filter-row",
      width: "100%",
      flexDirection: "row",
      gap: 1,
      alignItems: "center",
    },
    Text({ content: "Agent", fg: "#565f89" }),
    toolInput,
    Text({ content: "Project", fg: "#565f89" }),
    projectInput,
    Text({ content: "Days", fg: "#565f89" }),
    daysInput,
  )

  const shell = Box(
    {
      id: "list-shell",
      width: "100%",
      height: "100%",
      flexDirection: "column",
      padding: 1,
      gap: 1,
      backgroundColor: "#16161e",
    },
    Text({
      content:
        "Tab: fields · Enter: search/filters · Agent: claude|codex|cursor · Days: max age · s: OpenAI key · b: back",
      fg: "#bb9af7",
    }),
    searchInput,
    filterRow,
    select,
  )

  navigateBack = async () => {
    try {
      const f = filtersFromInputs(toolInput, projectInput, daysInput)
      const s = await apiSessions(base, 400, f)
      await showListScreen(renderer, base, s, listStateFromInputs(toolInput, projectInput, daysInput, searchInput))
    } catch {
      await showListScreen(
        renderer,
        base,
        initialSessions,
        listStateFromInputs(toolInput, projectInput, daysInput, searchInput),
      )
    }
  }

  openSettings = () => {
    void showOpenAISettings(renderer, base, async () => {
      try {
        const f = filtersFromInputs(toolInput, projectInput, daysInput)
        const s = await apiSessions(base, 400, f)
        await showListScreen(renderer, base, s, listStateFromInputs(toolInput, projectInput, daysInput, searchInput))
      } catch {
        await showListScreen(
          renderer,
          base,
          initialSessions,
          listStateFromInputs(toolInput, projectInput, daysInput, searchInput),
        )
      }
    })
  }

  renderer.root.add(shell)
  select.focus()
}

function showEmptyScreen(renderer: CliRenderer, base: string) {
  uiMode = "empty"
  detailSessionId = null
  settingsBack = null
  openSettings = () => {
    void showOpenAISettings(renderer, base, async () => {
      showEmptyScreen(renderer, base)
    })
  }
  emptyIndexResume = async () => {
    try {
      const s = await apiSessions(base, 400)
      if (s.length === 0) showEmptyScreen(renderer, base)
      else await showListScreen(renderer, base, s)
    } catch {
      showEmptyScreen(renderer, base)
    }
  }
  clearRoot(renderer)
  renderer.root.add(
    Box(
      {
        width: "100%",
        height: "100%",
        padding: 2,
        flexDirection: "column",
        gap: 1,
        backgroundColor: "#16161e",
      },
      Text({ content: "No sessions in index.", fg: "#f7768e" }),
      Text({ content: "Press i — full reindex with live progress (or run: sess index)", fg: "#a9b1d6" }),
      Text({ content: "Press s — set OpenAI API key (saved locally)", fg: "#a9b1d6" }),
      Text({ content: "Ctrl+C to exit", fg: "#565f89" }),
    ),
  )
}

async function main() {
  const base = apiBase()
  const ok = await apiHealth(base)
  if (!ok) {
    console.error(`Cannot reach API at ${base}/health — run: sess tui   (auto-starts server) or sess serve`)
    process.exit(1)
  }

  let sessions: ApiSession[] = []
  try {
    sessions = await apiSessions(base, 400)
  } catch (e) {
    console.error(e instanceof Error ? e.message : String(e))
    process.exit(1)
  }

  const renderer = await createCliRenderer({
    exitOnCtrlC: true,
    useMouse: true,
    backgroundColor: "#16161e",
    prependInputHandlers: [
      (seq) => {
        if (uiMode === "detail" && seq === "o" && detailSessionId) {
          void runResumeInNative(renderer, apiBase(), detailSessionId)
          return true
        }
        if (uiMode === "detail" && seq === "b") {
          void navigateBack?.()
          return true
        }
        if (uiMode === "settings" && seq === "b") {
          const back = settingsBack
          settingsBack = null
          if (back) void back()
          return true
        }
        if (uiMode === "list" && seq === "s" && openSettings) {
          openSettings()
          return true
        }
        if (uiMode === "empty" && seq === "s" && openSettings) {
          openSettings()
          return true
        }
        if (uiMode === "empty" && seq === "i") {
          const resume = emptyIndexResume
          if (resume) void showIndexingScreen(renderer, base, resume)
          return true
        }
        return false
      },
    ],
  })

  renderer.on("destroy", () => {
    navigateBack = null
    emptyIndexResume = null
    openSettings = null
    settingsBack = null
  })

  if (sessions.length === 0) {
    showEmptyScreen(renderer, base)
    return
  }

  await showListScreen(renderer, base, sessions)
}

await main()
