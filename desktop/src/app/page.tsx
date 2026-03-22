import HeatMap from "../components/HeatMap"
import SessionCard from "../components/SessionCard"
import { fetchSessions, fetchStats } from "../lib/api"

export default async function DashboardPage() {
  const [stats, recent] = await Promise.all([
    fetchStats().catch(() => []),
    fetchSessions({ limit: 10 }).catch(() => []),
  ])

  const totalSessions = recent.length
  const totalMessages = recent.reduce((total, session) => total + session.message_count, 0)
  const activeTools = [...new Set(recent.map((session) => session.source))]

  return (
    <div className="space-y-6">
      <section className="rounded-[24px] bg-[var(--surface-soft)] px-5 py-5 md:px-6">
        <p className="section-label">Overview</p>
        <div className="mt-3 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="max-w-2xl">
            <h2 className="text-3xl font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              A cleaner way to browse your AI coding history
            </h2>
            <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
              Keep the dashboard focused on what matters: recent activity, tool coverage, and the
              last year of session volume.
            </p>
          </div>
          <div className="rounded-2xl border border-black/6 bg-white px-4 py-3 text-sm text-[var(--text-secondary)]">
            A quick view of the latest 10 sessions
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <article className="subtle-panel rounded-[24px] px-5 py-4">
          <p className="section-label">Visible Sessions</p>
          <p className="mt-3 text-3xl font-semibold tracking-[-0.04em]">{totalSessions}</p>
        </article>
        <article className="subtle-panel rounded-[24px] px-5 py-4">
          <p className="section-label">Messages Indexed</p>
          <p className="mt-3 text-3xl font-semibold tracking-[-0.04em]">{totalMessages}</p>
        </article>
        <article className="subtle-panel rounded-[24px] px-5 py-4">
          <p className="section-label">Active Tools</p>
          <p className="mt-3 text-3xl font-semibold tracking-[-0.04em]">{activeTools.length}</p>
        </article>
      </section>

      <HeatMap data={stats} />

      <section className="space-y-4">
        <div className="flex items-end justify-between gap-3">
          <div>
            <p className="section-label">Recent Sessions</p>
            <h3 className="mt-2 text-xl font-semibold tracking-[-0.03em]">Recent activity</h3>
          </div>
          <p className="text-sm text-[var(--text-secondary)]">Sorted by last updated</p>
        </div>

        <div className="grid gap-3 xl:grid-cols-2">
          {recent.map((session) => (
            <SessionCard key={session.id} session={session} />
          ))}
        </div>
      </section>
    </div>
  )
}
