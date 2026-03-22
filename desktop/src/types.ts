export type SourceTool = "claude" | "codex" | "cursor"

export type MessageRole = "user" | "assistant" | "system" | "tool"

export interface Message {
  id: string
  session_id: string
  role: MessageRole
  content: string
  timestamp: string | null
  token_count: number | null
}

export interface Session {
  id: string
  source: SourceTool
  project_path: string | null
  title: string
  created_at: string
  updated_at: string
  message_count: number
  raw_path: string
  messages: Message[]
}

export interface SearchResult {
  session_id: string
  session_title: string
  source: SourceTool
  project_path: string | null
  snippet: string
  score: number
}

export interface HeatMapPoint {
  date: string
  tool: SourceTool
  count: number
}
