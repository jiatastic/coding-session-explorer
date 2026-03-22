import Link from "next/link"

export default function NotFound() {
  return (
    <div className="subtle-panel rounded-[24px] px-6 py-12 text-center">
      <p className="section-label">404</p>
      <h1 className="mt-2 text-2xl font-semibold tracking-[-0.04em]">Page not found</h1>
      <p className="mt-3 text-sm text-[var(--text-secondary)]">
        This route does not map to a session or page in the app.
      </p>
      <Link
        href="/"
        className="mt-6 inline-flex rounded-full bg-neutral-900 px-4 py-2 text-sm font-medium text-white"
      >
        Back to home
      </Link>
    </div>
  )
}
