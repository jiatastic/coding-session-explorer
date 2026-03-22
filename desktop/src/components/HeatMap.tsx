import { SourceTool } from "../types"

const TOOLS: SourceTool[] = ["claude", "codex", "cursor"]

const TOOL_LABEL: Record<SourceTool, string> = {
  claude: "Claude",
  codex: "Codex",
  cursor: "Cursor",
}

const LEVELS: Record<SourceTool, string[]> = {
  claude: ["bg-sky-50", "bg-sky-100", "bg-sky-200", "bg-sky-400"],
  codex: ["bg-emerald-50", "bg-emerald-100", "bg-emerald-200", "bg-emerald-400"],
  cursor: ["bg-violet-50", "bg-violet-100", "bg-violet-200", "bg-violet-400"],
}

type HeatMapPoint = {
  date: string
  tool: SourceTool
  count: number
}

function weekStart(date: Date) {
  const value = new Date(date)
  const day = value.getDay()
  value.setDate(value.getDate() - day)
  value.setHours(0, 0, 0, 0)
  return value
}

function formatWeek(date: Date) {
  return date.toISOString().slice(0, 10)
}

export default function HeatMap({ data }: { data: HeatMapPoint[] }) {
  const today = new Date()
  const firstWeek = weekStart(new Date(today.getFullYear(), today.getMonth(), today.getDate() - 51 * 7))
  const weeks = Array.from({ length: 52 }, (_, index) => {
    const value = new Date(firstWeek)
    value.setDate(firstWeek.getDate() + index * 7)
    return value
  })

  const counts = new Map<string, number>()
  data.forEach((point) => {
    const current = counts.get(`${point.tool}:${point.date}`) ?? 0
    counts.set(`${point.tool}:${point.date}`, current + point.count)
  })

  return (
    <section className="subtle-panel rounded-[24px] px-5 py-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="section-label">Activity</p>
          <h3 className="mt-2 text-xl font-semibold tracking-[-0.03em]">Activity over the last 52 weeks</h3>
        </div>
        <p className="text-sm text-[var(--text-secondary)]">One row per tool, one cell per week</p>
      </div>

      <div className="mt-5 space-y-4">
        {TOOLS.map((tool) => {
          const total = weeks.reduce((sum, weekDate) => {
            const dateKey = formatWeek(weekDate)
            return sum + (counts.get(`${tool}:${dateKey}`) ?? 0)
          }, 0)

          return (
            <div key={tool} className="grid gap-3 md:grid-cols-[88px_minmax(0,1fr)_72px] md:items-center">
              <div>
                <p className="text-sm font-medium text-[var(--text-primary)]">{TOOL_LABEL[tool]}</p>
              </div>

              <div className="grid grid-cols-13 gap-2 sm:grid-cols-26 xl:grid-cols-52">
                {weeks.map((weekDate) => {
                  const dateKey = formatWeek(weekDate)
                  const count = counts.get(`${tool}:${dateKey}`) ?? 0
                  const level =
                    count === 0 ? 0 : count < 3 ? 1 : count < 8 ? 2 : 3

                  return (
                    <div
                      key={`${tool}-${dateKey}`}
                      title={`${TOOL_LABEL[tool]} · ${dateKey} · ${count} sessions`}
                      className={`h-7 rounded-[10px] border border-white/80 ${LEVELS[tool][level]}`}
                    />
                  )
                })}
              </div>

              <div className="text-right text-sm text-[var(--text-secondary)]">{total}</div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
