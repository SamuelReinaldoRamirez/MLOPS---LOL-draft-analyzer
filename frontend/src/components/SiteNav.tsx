"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import BrandMark from "@/components/BrandMark";

const LINKS: { href: string; label: string }[] = [
  { href: "/", label: "Draft" },
  { href: "/search", label: "Find my games" },
];

/**
 * Sticky glass top navigation. The brand returns home; the two destinations
 * highlight the active route (gold text + an underline indicator). Kept as a
 * thin client component so the root layout can stay a server component.
 */
export default function SiteNav() {
  const pathname = usePathname();

  function isActive(href: string): boolean {
    if (href === "/") return pathname === "/";
    return pathname === href || pathname.startsWith(`${href}/`);
  }
  // The player journey (search → games → match → live) keeps "Find my games" lit.
  const onPlayerFlow = ["/search", "/games", "/match", "/live"].some(
    (p) => pathname === p || pathname.startsWith(`${p}/`) || pathname.startsWith(`${p}?`),
  );

  return (
    <header className="sticky top-0 z-50 border-b border-line bg-canvas/70 backdrop-blur-xl">
      <nav
        aria-label="Primary"
        className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6"
      >
        <Link
          href="/"
          className="group flex items-center gap-2.5 rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/60"
        >
          <span className="drop-shadow-[0_0_10px_rgba(200,170,110,0.35)] transition-transform duration-300 group-hover:scale-105">
            <BrandMark className="h-8 w-8" />
          </span>
          <span className="flex flex-col leading-none">
            <span className="font-display text-base font-bold tracking-wide text-ink">
              DRAFT<span className="text-gold">ORACLE</span>
            </span>
            <span className="mt-0.5 hidden text-[10px] font-medium uppercase tracking-[0.22em] text-ink-dim sm:block">
              LoL Win Predictor
            </span>
          </span>
        </Link>

        <div className="flex items-center gap-1">
          {LINKS.map((link) => {
            const active =
              link.href === "/search" ? onPlayerFlow : isActive(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={`relative whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/60 sm:px-3.5 ${
                  active
                    ? "text-gold"
                    : "text-ink-muted hover:bg-surface-2 hover:text-ink"
                }`}
              >
                {link.label}
                {active && (
                  <span className="absolute inset-x-3 -bottom-px h-0.5 rounded-full bg-gold-sheen" />
                )}
              </Link>
            );
          })}
        </div>
      </nav>
    </header>
  );
}
