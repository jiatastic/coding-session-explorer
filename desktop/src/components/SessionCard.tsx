import Link from "next/link"

import { Message, SourceTool } from "../types"

const TOOL_STYLE: Record<SourceTool, string> = {
  claude: "bg-sky-100 text-sky-700",
  codex: "bg-emerald-100 text-emerald-700",
  cursor: "bg-violet-100 text-violet-700",
}

type SessionCardProps = {
  session: {
    id: string
    title: string
    source: SourceTool
    project_path: string | null
    message_count: number
    updated_at: string
    messages: Message[]
  }
}

export default function SessionCard({ session }: SessionCardProps) {
  const updated = new Date(session.updated_at)

  return (
    <Link
      href={`/sessions/${session.id}`}
      className="group rounded-[24px] border border-black/6 bg-white px-5 py-4 shadow-[0_1px_2px_rgba(17,24,39,0.04)] transition hover:-translate-y-[1px] hover:border-black/10 hover:shadow-[0_10px_30px_rgba(17,24,39,0.06)]"
    >
      <div className="flex items-start justify-between gap-3">
        <span className={`tool-chip ${TOOL_STYLE[session.source]}`}>{session.source}</span>
        <span className="text-xs text-[var(--text-muted)]">{updated.toLocaleDateString()}</span>
      </div>

      <h3 className="mt-4 line-clamp-2 text-lg font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
        {session.title}
      </h3>

      <p className="mt-2 line-clamp-1 text-sm text-[var(--text-secondary)]">
        {session.project_path || "Unknown project"}
      </p>

      <div className="mt-4 flex items-center justify-between gap-3 border-t border-black/6 pt-4 text-sm text-[var(--text-secondary)]">
        <span>{session.message_count} messages</span>
        <span className="transition group-hover:text-[var(--text-primary)]">Open</span>
      </div>
    </Link>
  )
}
