import Link from "next/link"
import { Fragment } from "react"

import { SearchResult as SearchResultType, SourceTool } from "../types"

const TOOL_STYLE: Record<SourceTool, string> = {
  claude: "bg-sky-100 text-sky-700",
  codex: "bg-emerald-100 text-emerald-700",
  cursor: "bg-violet-100 text-violet-700",
}

function escape(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

function renderSnippet(snippet: string, query: string) {
  if (!query.trim()) return snippet

  const regex = new RegExp(`(${escape(query)})`, "gi")
  const parts = snippet.split(regex)

  return parts.map((part, index) => {
    if (part.toLowerCase() === query.toLowerCase()) {
      return (
        <mark
          key={`${part}-${index}`}
          className="rounded bg-amber-100 px-1 py-0.5 text-inherit"
        >
          {part}
        </mark>
      )
    }

    return <Fragment key={`${part}-${index}`}>{part}</Fragment>
  })
}

export default function SearchResult({ result, query }: { result: SearchResultType; query: string }) {
  const width = `${Math.max(12, Math.min(100, result.score * 100))}%`

  return (
    <Link
      href={`/sessions/${result.session_id}`}
      className="rounded-[24px] border border-black/6 bg-white px-5 py-4 shadow-[0_1px_2px_rgba(17,24,39,0.04)] transition hover:-translate-y-[1px] hover:border-black/10 hover:shadow-[0_10px_30px_rgba(17,24,39,0.06)]"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className={`tool-chip ${TOOL_STYLE[result.source]}`}>{result.source}</span>
        <div className="flex items-center gap-3 text-sm text-[var(--text-secondary)]">
          <div className="h-2 w-24 overflow-hidden rounded-full bg-neutral-100">
            <div className="h-full rounded-full bg-neutral-900" style={{ width }} />
          </div>
          <span>{result.score.toFixed(3)}</span>
        </div>
      </div>

      <h3 className="mt-4 text-lg font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
        {result.session_title}
      </h3>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        {result.project_path || "No project"}
      </p>
      <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-[var(--text-primary)]">
        {renderSnippet(result.snippet, query)}
      </p>
    </Link>
  )
}
