"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "./auth";
import { Spinner } from "./ui";
import { LogoMark } from "@/components/marketing/Nav";

const links = [
  { href: "/feed", label: "Feed" },
  { href: "/tracker", label: "Tracker" },
  { href: "/settings", label: "Settings" },
];

/** Account menu: email, profile (evidence) and log out, behind one round button. */
function AccountMenu({ email, onLogout }: { email: string; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);
  return (
    <div ref={ref} className="relative">
      <button type="button" aria-expanded={open} aria-haspopup="true" onClick={() => setOpen((v) => !v)}
        className="flex h-11 w-11 items-center justify-center rounded-full bg-ink font-display text-base text-on-dark shadow-button">
        <span className="sr-only">Account menu</span>
        <span aria-hidden="true">{email.slice(0, 1).toUpperCase()}</span>
      </button>
      {open && (
        <div className="absolute right-0 top-[calc(100%+10px)] w-64 rounded-panel bg-on-dark p-2 shadow-nav-scrolled">
          <p className="truncate px-3 py-2 text-sm text-muted">{email}</p>
          <Link href="/onboarding" onClick={() => setOpen(false)} className="flex min-h-11 items-center rounded-card px-3 text-[15px] text-ink hover:bg-quiet">Profile and evidence</Link>
          <button type="button" onClick={onLogout} className="flex min-h-11 w-full items-center rounded-card px-3 text-left text-[15px] text-ink hover:bg-quiet">Log out</button>
        </div>
      )}
    </div>
  );
}

// App header = the marketing floating pill (spec §3): logo, three destinations, account.
export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-canvas">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-full focus:bg-on-dark focus:px-3 focus:py-2">Skip to content</a>
      <header className="sticky top-4 z-30 px-4">
        <div className="mx-auto flex h-[60px] max-w-[680px] items-center justify-between gap-2 rounded-nav bg-on-dark py-2 pl-4 pr-2 shadow-nav">
          <Link href="/feed" className="inline-flex min-h-11 items-center gap-2 text-ink">
            <LogoMark />
            <span className="hidden font-display text-[22px] tracking-[-0.04em] sm:inline">Fitwise</span>
          </Link>
          <nav aria-label="Main" className="flex items-center gap-1">
            {links.map((l) => {
              const active = pathname === l.href || (l.href === "/feed" && pathname.startsWith("/jobs"));
              return (
                <Link
                  key={l.href}
                  href={l.href}
                  aria-current={active ? "page" : undefined}
                  className={`inline-flex min-h-11 items-center rounded-pill px-3 text-[15px] font-medium sm:px-4 sm:text-base ${
                    active ? "bg-highlight text-ink" : "text-ink hover:bg-quiet"
                  }`}
                >
                  {l.label}
                </Link>
              );
            })}
          </nav>
          <AccountMenu email={user.email} onLogout={logout} />
        </div>
      </header>
      <main id="main" className="mx-auto max-w-[1072px] px-4 pb-20 pt-14">{children}</main>
    </div>
  );
}
