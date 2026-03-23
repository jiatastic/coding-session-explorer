import type { Metadata } from "next"

import SidebarNav from "../components/SidebarNav"
import "./globals.css"

export const metadata: Metadata = {
  title: "Coding Session Explorer",
  description: "Local AI session explorer",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen bg-[var(--app-bg)] px-4 py-5 text-[var(--text-primary)] md:px-6 md:py-8">
          <div className="mx-auto grid min-h-[calc(100vh-2.5rem)] max-w-[1440px] gap-5 lg:grid-cols-[248px_minmax(0,1fr)]">
            <aside className="panel flex flex-col justify-between rounded-[28px] p-5">
              <div className="space-y-8">
                <div className="space-y-2">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-black/5 bg-neutral-950 text-sm font-semibold text-white">
                      CS
                    </div>
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
                        Local Index
                      </p>
                      <h1 className="text-xl font-semibold tracking-[-0.03em]">
                        Coding Session Explorer
                      </h1>
                    </div>
                  </div>
                  <p className="max-w-[18rem] text-sm leading-6 text-[var(--text-secondary)]">
                    Browse Claude, Codex, and Cursor session history from one local index.
                  </p>
                </div>
                <SidebarNav />
              </div>

              <div className="rounded-3xl border border-black/6 bg-neutral-50 px-4 py-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[var(--text-muted)]">
                  Workspace
                </p>
                <p className="mt-2 text-sm font-medium text-[var(--text-primary)]">
                  Local-first browsing
                </p>
                <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                  Search, filter, and inspect everything directly from your machine.
                </p>
              </div>
            </aside>

            <main className="panel rounded-[28px] p-4 md:p-6">{children}</main>
          </div>
        </div>
      </body>
    </html>
  )
}
