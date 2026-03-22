import { HeatMapPoint, SearchResult, Session } from "../types"

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000"

type QueryValue = string | number | undefined

async function apiRequest<T>(path: string, params: Record<string, QueryValue> = {}): Promise<T> {
  const search = new URLSearchParams()

  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined) return
    search.set(key, String(value))
  })

  const target = new URL(`${path}?${search.toString()}`, API_BASE)
  const response = await fetch(target)

  if (!response.ok) {
    throw new Error(`request failed: ${response.status} ${response.statusText}`)
  }

  return response.json()
}

export async function fetchStats() {
  return apiRequest<HeatMapPoint[]>("/stats")
}

export async function fetchSessions(params: {
  tool?: string
  project?: string
  days?: number
  limit?: number
  offset?: number
} = {}): Promise<Session[]> {
  return apiRequest<Session[]>("/sessions", {
    tool: params.tool,
    project: params.project,
    days: params.days,
    limit: params.limit,
    offset: params.offset,
  })
}

export async function fetchSession(id: string): Promise<Session> {
  return apiRequest<Session>(`/sessions/${id}`)
}

export async function fetchSearchResults(
  query: string,
  limit = 20,
  mode: "auto" | "semantic" | "fulltext" = "auto",
): Promise<SearchResult[]> {
  return apiRequest<SearchResult[]>("/search", {
    q: query,
    limit,
    mode,
  })
}

export { API_BASE }
