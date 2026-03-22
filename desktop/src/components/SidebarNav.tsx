"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/sessions", label: "Sessions" },
  { href: "/search", label: "Search" },
]

export default function SidebarNav() {
  const pathname = usePathname()

  return (
    <nav className="space-y-1">
      {LINKS.map((link) => {
        const active =
          link.href === "/" ? pathname === "/" : pathname === link.href || pathname.startsWith(`${link.href}/`)

        return (
          <Link
            key={link.href}
            href={link.href}
            className={`nav-link ${active ? "nav-link-active" : ""}`}
          >
            <span className={`nav-link-dot ${active ? "bg-neutral-900" : "bg-neutral-300"}`} />
            {link.label}
          </Link>
        )
      })}
    </nav>
  )
}
