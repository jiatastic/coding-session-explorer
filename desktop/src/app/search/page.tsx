"use client"

import { useEffect, useState } from "react"

import SearchResult from "../../components/SearchResult"
import { fetchSearchResults } from "../../lib/api"
import { SearchResult as SearchResultType } from "../../types"

const MODES: Array<{ value: "auto" | "semantic" | "fulltext"; label: string }> = [
  { value: "auto", label: "Auto" },
  { value: "semantic", label: "Semantic" },
  { value: "fulltext", label: "Fulltext" },
]

export default function SearchPage() {
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<SearchResultType[]>([])
  const [mode, setMode] = useState<"auto" | "semantic" | "fulltext">("auto")

  useEffect(() => {
    if (!query.trim()) return

    const handle = window.setTimeout(async () => {
      try {
        const data = await fetchSearchResults(query, 20, mode)
        setResults(data)
      } catch {
        setResults([])
      }
    }, 300)

    return () => window.clearTimeout(handle)
  }, [mode, query])

  const visibleResults = query.trim() ? results : []

  return (
    <div className="space-y-5">
      <section className="rounded-[24px] bg-[var(--surface-soft)] px-5 py-5">
        <p className="section-label">Search</p>
        <div className="mt-3 flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-2xl">
            <h1 className="text-2xl font-semibold tracking-[-0.04em]">Search across sessions</h1>
            <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
              Keep the surface minimal: one primary input, one lightweight mode switch, and clear
              results.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            {MODES.map((item) => (
              <button
                key={item.value}
                type="button"
                onClick={() => setMode(item.value)}
                className={`rounded-full px-4 py-2 text-sm font-medium transition ${
                  mode === item.value
                    ? "bg-neutral-900 text-white"
                    : "border border-black/6 bg-white text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-5">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="field"
            placeholder="Search conversations, fixes, errors, or code snippets"
          />
        </div>
      </section>

      {visibleResults.length === 0 ? (
        <div className="subtle-panel rounded-[24px] px-6 py-10 text-center text-sm text-[var(--text-secondary)]">
          Start typing to search your indexed sessions
        </div>
      ) : (
        <div className="grid gap-3">
          {visibleResults.map((result) => (
            <SearchResult key={result.session_id} result={result} query={query} />
          ))}
        </div>
      )}
    </div>
  )
}
