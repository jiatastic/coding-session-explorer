"use client"

import { useEffect, useMemo, useState } from "react"

import SessionCard from "../../components/SessionCard"
import { fetchSessions } from "../../lib/api"
import { Session, SourceTool } from "../../types"

const TOOLS: SourceTool[] = ["claude", "codex", "cursor"]

export default function SessionsPage() {
  const [toolFilters, setToolFilters] = useState<SourceTool[]>(TOOLS)
  const [projectFilter, setProjectFilter] = useState("")
  const [daysFilter, setDaysFilter] = useState<number | undefined>()
  const [sessions, setSessions] = useState<Session[]>([])

  const fetchParams = useMemo(
    () => ({
      project: projectFilter || undefined,
      days: daysFilter,
      limit: 100,
    }),
    [daysFilter, projectFilter],
  )

  useEffect(() => {
    const controller = new AbortController()

    void (async () => {
      const loaded = await Promise.all(
        TOOLS.map((tool) =>
          toolFilters.includes(tool)
            ? fetchSessions({
                ...fetchParams,
                tool,
              }).catch(() => [])
            : Promise.resolve([]),
        ),
      )

      if (controller.signal.aborted) return
      setSessions(loaded.flat())
    })()

    return () => controller.abort()
  }, [fetchParams, toolFilters])

  const filteredSessions = useMemo(() => {
    const normalized = projectFilter.trim().toLowerCase()
    if (!normalized) return sessions

    return sessions.filter((session) =>
      (session.project_path || "").toLowerCase().includes(normalized),
    )
  }, [projectFilter, sessions])

  const toggleTool = (tool: SourceTool) => {
    setToolFilters((current) =>
      current.includes(tool) ? current.filter((value) => value !== tool) : [...current, tool],
    )
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[260px_minmax(0,1fr)]">
      <aside className="subtle-panel h-fit rounded-[24px] p-5">
        <div>
          <p className="section-label">Filters</p>
          <h2 className="mt-2 text-xl font-semibold tracking-[-0.03em]">Refine sessions</h2>
        </div>

        <div className="mt-6 space-y-6">
          <section>
            <p className="mb-3 text-sm font-medium text-[var(--text-primary)]">Tool</p>
            <div className="space-y-2">
              {TOOLS.map((tool) => {
                const active = toolFilters.includes(tool)

                return (
                  <button
                    key={tool}
                    type="button"
                    onClick={() => toggleTool(tool)}
                    className={`flex w-full items-center justify-between rounded-2xl border px-3 py-2.5 text-sm transition ${
                      active
                        ? "border-neutral-900 bg-neutral-900 text-white"
                        : "border-black/6 bg-white text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                    }`}
                  >
                    <span className="capitalize">{tool}</span>
                    <span>{active ? "On" : "Off"}</span>
                  </button>
                )
              })}
            </div>
          </section>

          <section>
            <p className="mb-3 text-sm font-medium text-[var(--text-primary)]">Project</p>
            <input
              value={projectFilter}
              onChange={(event) => setProjectFilter(event.target.value)}
              className="field"
              placeholder="Filter by project path"
            />
          </section>

          <section>
            <p className="mb-3 text-sm font-medium text-[var(--text-primary)]">Age</p>
            <input
              type="number"
              min={1}
              value={daysFilter ?? ""}
              onChange={(event) =>
                setDaysFilter(event.target.value ? Number(event.target.value) : undefined)
              }
              className="field"
              placeholder="Limit to the last N days"
            />
          </section>
        </div>
      </aside>

      <section className="space-y-4">
        <div className="flex flex-col gap-3 rounded-[24px] bg-[var(--surface-soft)] px-5 py-5 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="section-label">Sessions</p>
            <h1 className="mt-2 text-2xl font-semibold tracking-[-0.04em]">Indexed sessions</h1>
          </div>
          <p className="text-sm text-[var(--text-secondary)]">{filteredSessions.length} results</p>
        </div>

        <div className="grid gap-3 xl:grid-cols-2">
          {filteredSessions.map((session) => (
            <SessionCard key={session.id} session={session} />
          ))}
        </div>
      </section>
    </div>
  )
}
