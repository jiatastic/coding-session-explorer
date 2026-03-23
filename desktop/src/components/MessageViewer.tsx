import ReactMarkdown from "react-markdown"
import rehypeHighlight from "rehype-highlight"

import { Message } from "../types"

const ROLE_STYLE: Record<
  Message["role"],
  { align: string; tone: string; label: string }
> = {
  user: {
    align: "justify-end",
    tone: "bg-neutral-900 text-white border-neutral-900",
    label: "User",
  },
  assistant: {
    align: "justify-start",
    tone: "bg-white text-[var(--text-primary)] border-black/6",
    label: "Assistant",
  },
  system: {
    align: "justify-start",
    tone: "bg-amber-50 text-amber-900 border-amber-200",
    label: "System",
  },
  tool: {
    align: "justify-start",
    tone: "bg-violet-50 text-violet-900 border-violet-200",
    label: "Tool",
  },
}

export default function MessageViewer({ messages }: { messages: Message[] }) {
  return (
    <div className="space-y-4">
      {messages.map((message) => {
        const style = ROLE_STYLE[message.role]
        const timestamp = message.timestamp ? new Date(message.timestamp).toLocaleString() : null

        return (
          <div key={message.id} className={`flex ${style.align}`}>
            <article className={`w-full max-w-3xl rounded-[24px] border px-5 py-4 shadow-[0_1px_2px_rgba(17,24,39,0.04)] ${style.tone}`}>
              <div className="mb-3 flex flex-wrap items-center gap-3 text-xs font-medium uppercase tracking-[0.18em] opacity-75">
                <span>{style.label}</span>
                {timestamp ? <span>{timestamp}</span> : null}
              </div>

              <div className="prose max-w-none text-sm leading-7 prose-headings:mb-3 prose-headings:mt-0 prose-p:my-3 prose-pre:rounded-2xl prose-pre:border prose-pre:border-black/6 prose-pre:bg-black/90 prose-code:rounded prose-code:bg-black/5 prose-code:px-1 prose-code:py-0.5 prose-code:text-[0.9em] prose-code:before:content-[''] prose-code:after:content-['']">
                <ReactMarkdown rehypePlugins={[rehypeHighlight]}>{message.content}</ReactMarkdown>
              </div>
            </article>
          </div>
        )
      })}
    </div>
  )
}
