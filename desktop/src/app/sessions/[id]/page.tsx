import Link from "next/link"

import MessageViewer from "../../../components/MessageViewer"
import { fetchSession } from "../../../lib/api"
import { Session } from "../../../types"

const TOOL_TONE = {
  claude: "bg-sky-100 text-sky-700",
  codex: "bg-emerald-100 text-emerald-700",
  cursor: "bg-violet-100 text-violet-700",
}

export default async function SessionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const resolvedParams = await params
  let session: Session | null = null

  try {
    session = await fetchSession(resolvedParams.id)
  } catch {
    session = null
  }

  if (!session) {
    return (
      <div className="subtle-panel rounded-[24px] px-6 py-10 text-center">
        <h1 className="text-xl font-semibold tracking-[-0.03em]">Session not found</h1>
        <p className="mt-2 text-sm text-[var(--text-secondary)]">No session matched this id.</p>
        <Link href="/sessions" className="mt-5 inline-flex rounded-full bg-neutral-900 px-4 py-2 text-sm font-medium text-white">
          Back to sessions
        </Link>
      </div>
    )
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
      <section className="space-y-4">
        <div className="rounded-[24px] bg-[var(--surface-soft)] px-5 py-5">
          <Link href="/sessions" className="text-sm text-[var(--text-secondary)] transition hover:text-[var(--text-primary)]">
            Sessions
          </Link>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <span className={`tool-chip ${TOOL_TONE[session.source]}`}>{session.source}</span>
            <span className="text-sm text-[var(--text-secondary)]">
              {new Date(session.updated_at).toLocaleString()}
            </span>
          </div>
          <h1 className="mt-3 max-w-4xl text-3xl font-semibold tracking-[-0.05em]">
            {session.title}
          </h1>
        </div>

        <MessageViewer messages={session.messages} />
      </section>

      <aside className="subtle-panel h-fit rounded-[24px] p-5">
        <p className="section-label">Metadata</p>
        <h2 className="mt-2 text-xl font-semibold tracking-[-0.03em]">Session details</h2>

        <dl className="mt-6 space-y-5">
          <div>
            <dt className="text-sm text-[var(--text-muted)]">Tool</dt>
            <dd className="mt-1 text-sm font-medium capitalize text-[var(--text-primary)]">
              {session.source}
            </dd>
          </div>
          <div>
            <dt className="text-sm text-[var(--text-muted)]">Project</dt>
            <dd className="mt-1 break-all text-sm font-medium text-[var(--text-primary)]">
              {session.project_path || "Unknown"}
            </dd>
          </div>
          <div>
            <dt className="text-sm text-[var(--text-muted)]">Created</dt>
            <dd className="mt-1 text-sm font-medium text-[var(--text-primary)]">
              {new Date(session.created_at).toLocaleString()}
            </dd>
          </div>
          <div>
            <dt className="text-sm text-[var(--text-muted)]">Messages</dt>
            <dd className="mt-1 text-sm font-medium text-[var(--text-primary)]">
              {session.message_count}
            </dd>
          </div>
          <div>
            <dt className="text-sm text-[var(--text-muted)]">Raw Path</dt>
            <dd className="mt-1 break-all text-sm leading-6 text-[var(--text-secondary)]">
              {session.raw_path}
            </dd>
          </div>
        </dl>
      </aside>
    </div>
  )
}
