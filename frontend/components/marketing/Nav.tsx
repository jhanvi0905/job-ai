"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { ArrowChip, CTA_LABEL, pillClass } from "./shared";
import { EASE } from "./motion";

const links = [
  { href: "#how", label: "How it works" },
  { href: "#different", label: "Why it's different" },
  { href: "#pricing", label: "Pricing" },
];

/** Fitwise mark: a black disc with a tick that doubles as an upward path. */
export function LogoMark({ size = 26 }: { size?: number }) {
  return (
    <svg aria-hidden="true" width={size} height={size} viewBox="0 0 26 26">
      <circle cx="13" cy="13" r="13" fill="currentColor" />
      <path d="M7.5 13.5l3.6 3.6 7.4-8.6" fill="none" stroke="var(--on-dark)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// Job: compel. Lever: the next step is always one tap away (floating pill, one CTA).
export function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 40);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);

  useEffect(() => {
    if (!open) return;
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [open]);

  return (
    <header className="pointer-events-none fixed inset-x-0 top-4 z-40 px-4">
      <div
        className={`pointer-events-auto mx-auto flex h-[60px] max-w-[680px] items-center justify-between gap-3 rounded-nav bg-on-dark py-2 pl-4 pr-2 transition-shadow duration-300 ${scrolled ? "shadow-nav-scrolled" : "shadow-nav"}`}
      >
        <Link href="/" className="inline-flex min-h-11 items-center gap-2 text-ink">
          <LogoMark />
          <span className="font-display text-[22px] tracking-[-0.04em]">Fitwise</span>
        </Link>
        <nav aria-label="Sections" className="hidden items-center gap-5 md:flex">
          {links.map((l) => (
            <a key={l.href} href={l.href} className="inline-flex min-h-11 items-center text-base font-medium text-ink hover:text-muted">{l.label}</a>
          ))}
        </nav>
        <div className="flex items-center gap-1">
          <Link href="/signup" className={pillClass("black", "!h-11 text-[15px] sm:text-base")}>
            <span className="sm:hidden">Free fit check</span>
            <span className="hidden sm:inline">{CTA_LABEL}</span>
            <ArrowChip />
          </Link>
          <button
            type="button" aria-expanded={open} aria-controls="nav-sheet" onClick={() => setOpen((v) => !v)}
            className="inline-flex h-11 w-11 items-center justify-center rounded-full text-ink hover:bg-quiet md:hidden"
          >
            <span className="sr-only">{open ? "Close menu" : "Open menu"}</span>
            <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              {open ? <path d="M6 6l12 12M18 6 6 18" /> : <path d="M4 8h16M4 16h16" />}
            </svg>
          </button>
        </div>
      </div>
      <AnimatePresence>
        {open && (
          <motion.nav
            id="nav-sheet" aria-label="Sections"
            initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.25, ease: EASE }}
            className="pointer-events-auto mx-auto mt-2 max-w-[680px] rounded-panel bg-on-dark p-2 shadow-nav md:hidden"
          >
            {[...links, { href: "/login", label: "Log in" }].map((l) => (
              <a key={l.href} href={l.href} onClick={() => setOpen(false)}
                className="flex min-h-12 items-center rounded-card px-4 text-base font-medium text-ink hover:bg-quiet">
                {l.label}
              </a>
            ))}
          </motion.nav>
        )}
      </AnimatePresence>
    </header>
  );
}
