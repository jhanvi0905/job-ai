"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Achievement, Application, FeedItem } from "@/lib/product-types";
import { CountUp } from "./CountUp";

/*
 * Retention surfaces (GO_TO_MARKET §6c), built only from data the API already returns.
 * Rules: no streaks, no fake urgency, every nudge dismissible, localStorage is a
 * convenience that may be missing (private mode, blocked storage) so every access is
 * wrapped and the UI still renders without it.
 */

const KEY = {
  lastVisit: "fitwise.feed.lastVisit",
  weekHidden: "fitwise.feed.weekCardHidden",
  followupOff: "fitwise.tracker.followupOff",
  followupDismissed: "fitwise.tracker.followupDismissed",
};
const DAY = 86_400_000;

export const store = {
  get(k: string): string | null {
    try { return window.localStorage.getItem(k); } catch { return null; }
  },
  set(k: string, v: string) {
    try { window.localStorage.setItem(k, v); } catch { /* storage unavailable */ }
  },
};

const ts = (s: string | null | undefined) => {
  if (!s) return NaN;
  const t = Date.parse(s);
  return Number.isFinite(t) ? t : NaN;
};

/* ---------------- New matches since last visit (feed header) ---------------- */

// Previous visit, read once per page session. Module-level so React StrictMode's
// double effects (and re-mounts while navigating) don't overwrite it before use.
let sessionPrev: number | null | undefined;
function readPrevVisitOnce(): number | null {
  if (sessionPrev === undefined) {
    const raw = store.get(KEY.lastVisit);
    const t = raw ? Number(raw) : NaN;
    sessionPrev = Number.isFinite(t) ? t : null;
    store.set(KEY.lastVisit, String(Date.now()));
  }
  return sessionPrev;
}

/**
 * Previous feed visit time, then records this visit. Returns undefined until
 * mounted, null on a first visit (or when storage is unavailable).
 */
export function useLastVisit(): number | null | undefined {
  const [prev, setPrev] = useState<number | null | undefined>(undefined);
  useEffect(() => {
    const t = readPrevVisitOnce();
    const id = setTimeout(() => setPrev(t), 0);
    return () => clearTimeout(id);
  }, []);
  return prev;
}

/**
 * The feed only carries `posted_at` (when the employer posted), not when we scored it.
 * So "new" means posted after your last visit. When no item has a usable timestamp we
 * fall back to items that are not in your tracker yet, and say so in the label.
 */
export function newMatchInfo(items: FeedItem[], lastVisit: number | null | undefined, apps: Application[] | null) {
  const dated = items.filter((i) => Number.isFinite(ts(i.posted_at)));
  if (dated.length > 0) {
    if (lastVisit == null) return { mode: "none" as const, ids: new Set<number>(), count: 0 };
    const ids = new Set(dated.filter((i) => ts(i.posted_at) > lastVisit).map((i) => i.job_id));
    return { mode: "new" as const, ids, count: ids.size };
  }
  if (!apps) return { mode: "none" as const, ids: new Set<number>(), count: 0 };
  const tracked = new Set(apps.map((a) => a.job_id));
  const count = items.filter((i) => !tracked.has(i.job_id)).length;
  return { mode: "unreviewed" as const, ids: new Set<number>(), count };
}

export function NewMatchBadge({ info }: { info: ReturnType<typeof newMatchInfo> }) {
  const [hidden, setHidden] = useState(false);
  if (hidden || info.count === 0 || info.mode === "none") return null;
  const text = info.mode === "new"
    ? `${info.count} new ${info.count === 1 ? "match" : "matches"} posted since your last visit`
    : `${info.count} ${info.count === 1 ? "match" : "matches"} not in your tracker yet`;
  return (
    <p role="status" className="inline-flex items-center gap-2 rounded-full bg-on-dark py-0.5 pl-4 pr-0.5 text-[15px] text-ink shadow-float">
      <span aria-hidden="true" className="h-2 w-2 rounded-full bg-alert" />
      {text}
      <button type="button" onClick={() => setHidden(true)} aria-label="Dismiss new matches notice"
        className="inline-flex h-11 w-11 items-center justify-center rounded-full text-muted hover:bg-quiet hover:text-ink">
        <svg aria-hidden="true" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M6 6l12 12M18 6 6 18" /></svg>
      </button>
    </p>
  );
}

/* ---------------- This week progress card (feed) ---------------- */

export function weekStats(apps: Application[], now: number) {
  const since = now - 7 * DAY;
  const recent = (a: Application) => ts(a.updated_at) >= since;
  return {
    reviewed: apps.filter(recent).length,
    tailored: apps.filter((a) => a.status === "tailored" && recent(a)).length,
    applied: apps.filter((a) => ts(a.applied_on) >= since).length,
    awaiting: apps.filter((a) => a.status === "applied").length,
  };
}

export function ThisWeekCard({ apps }: { apps: Application[] | null }) {
  const [hidden, setHidden] = useState<boolean | null>(null);
  const [now, setNow] = useState(0);
  useEffect(() => {
    const id = setTimeout(() => { setHidden(store.get(KEY.weekHidden) === "1"); setNow(Date.now()); }, 0);
    return () => clearTimeout(id);
  }, []);
  if (!apps || hidden === null) return null;
  const toggle = (v: boolean) => { store.set(KEY.weekHidden, v ? "1" : "0"); setHidden(v); };
  if (hidden) {
    return (
      <button type="button" onClick={() => toggle(false)} className="inline-flex min-h-11 items-center text-[15px] text-muted underline-offset-4 hover:text-ink hover:underline">
        Show this week&apos;s progress
      </button>
    );
  }
  const s = weekStats(apps, now);
  const cells: Array<[string, number, string, string]> = [
    ["Reviewed", s.reviewed, "saved or updated in your tracker", "bg-cyan"],
    ["Tailored", s.tailored, "now at the tailored stage", "bg-yellow"],
    ["Applied", s.applied, "applied in the last 7 days", "bg-salmon"],
    ["Awaiting", s.awaiting, "applied, no update yet", "bg-faint"],
  ];
  const max = Math.max(1, ...cells.map((c) => c[1]));
  // Styled like Grovia's "Daily Average" mini-card: label, one big number, a quiet
  // delta line, and one bar per stat. Real counts only; nothing resets after a break.
  return (
    <section aria-labelledby="week-h" className="rounded-[22px] bg-card p-5 shadow-float sm:p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 id="week-h" className="text-[15px] text-muted">This week</h2>
          <p className="mt-1 font-display text-[34px] leading-none tracking-[-0.05em] text-ink">
            <CountUp value={s.applied} /> <span className="text-[20px] tracking-[-0.04em]">applied</span>
          </p>
          <p className="mt-2 text-[13px] text-muted">From your tracker, last 7 days. Taking a break is fine; nothing here resets.</p>
        </div>
        <button type="button" onClick={() => toggle(true)} className="inline-flex min-h-11 shrink-0 items-center rounded-pill px-3 text-[15px] text-muted hover:bg-quiet hover:text-ink">
          Hide
        </button>
      </div>
      <dl className="mt-5 grid grid-cols-4 gap-3">
        {cells.map(([k, v, hint, bar]) => (
          <div key={k} className="flex flex-col items-center">
            <dt className="order-last mt-2 text-[12px] text-muted">{k}<span className="sr-only">: {hint}</span></dt>
            <dd className="flex w-full flex-col items-center">
              <span className="mb-2 font-display text-xl tabular-nums tracking-[-0.04em] text-ink"><CountUp value={v} /></span>
              <span aria-hidden="true" className="flex h-16 w-full max-w-[36px] items-end overflow-hidden rounded-[6px] bg-quiet">
                <span className={`w-full rounded-[6px] ${bar} transition-[height] duration-700 ease-quint`} style={{ height: `${Math.max(6, (v / max) * 100)}%` }} />
              </span>
            </dd>
          </div>
        ))}
      </dl>
      {apps.length === 0 && (
        <p className="mt-4 text-[15px] text-muted">Save a job from the list below and it starts counting here.</p>
      )}
    </section>
  );
}

/* ---------------- Tracker follow-up nudge ---------------- */

function readDismissed(): Set<string> {
  try { return new Set(JSON.parse(store.get(KEY.followupDismissed) ?? "[]") as string[]); } catch { return new Set(); }
}

/** "Applied N days ago. Follow up?" for status 'applied' older than 7 days. Dismissible per job, or off entirely. */
export function FollowUpNudge({ a }: { a: Application }) {
  // Days since applying; computed after mount (clock reads are not render-pure).
  const [days, setDays] = useState<number | null>(null);
  const since = ts(a.applied_on) || ts(a.updated_at);

  useEffect(() => {
    if (a.status !== "applied" || !Number.isFinite(since)) return;
    const d = Math.floor((Date.now() - since) / DAY);
    const off = store.get(KEY.followupOff) === "1" || readDismissed().has(String(a.job_id));
    const id = setTimeout(() => setDays(d >= 7 && !off ? d : null), 0);
    return () => clearTimeout(id);
  }, [a.status, a.job_id, since]);

  if (days === null) return null;
  function dismiss() {
    const s = readDismissed(); s.add(String(a.job_id));
    store.set(KEY.followupDismissed, JSON.stringify([...s]));
    setDays(null);
  }
  function turnOff() { store.set(KEY.followupOff, "1"); setDays(null); }

  return (
    <div className="rounded-[14px] bg-highlight p-3 text-sm text-ink">
      <p className="font-medium">Applied {days} days ago. Follow up?</p>
      <p className="mt-0.5 text-[13px] text-muted">A short, polite note to the recruiter is normal after a week. Add it to your notes once sent.</p>
      <div className="mt-1 flex flex-wrap gap-x-2">
        <button type="button" onClick={dismiss} className="inline-flex min-h-11 items-center font-medium underline-offset-4 hover:underline">Dismiss</button>
        <button type="button" onClick={turnOff} className="inline-flex min-h-11 items-center text-muted underline-offset-4 hover:text-ink hover:underline">Turn off follow-up reminders</button>
      </div>
    </div>
  );
}

/* ---------------- Profile completeness (onboarding / settings) ---------------- */

/** Heuristic target (not a measured threshold): enough evidence for matching to work with. */
const TARGET = 8;

export function ProfileMeter({ items, showLink = false }: { items: Achievement[]; showLink?: boolean }) {
  const n = items.length;
  const checked = items.filter((a) => a.user_edited).length;
  const done = Math.min(n, TARGET) + Math.min(checked, TARGET);
  const total = TARGET * 2;
  const more = Math.max(0, TARGET - n);
  const message = more > 0
    ? `${more} more ${more === 1 ? "achievement sharpens" : "achievements sharpen"} your matches. Add them to your resume and upload it again.`
    : checked < n
      ? `${n - checked} not yet edited by you. Each one you check and tweak becomes a bullet you can defend.`
      : "Your evidence is in good shape. Every match and rewrite draws on it.";
  return (
    <div className="rounded-[22px] bg-card p-5 text-ink shadow-float">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-[15px] text-muted">Your evidence</p>
        <p className="text-[13px] text-muted">{n} {n === 1 ? "achievement" : "achievements"} &middot; {checked} edited by you</p>
      </div>
      <div role="meter" aria-label="Profile completeness" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}
        aria-valuetext={`${n} achievements, ${checked} edited by you`} className="mt-3 flex h-2.5 gap-0.5 overflow-hidden rounded-full bg-quiet">
        <div className="h-full rounded-full bg-cyan transition-[width] duration-700 ease-quint" style={{ width: `${(Math.min(n, TARGET) / total) * 100}%` }} />
        <div className="h-full rounded-full bg-yellow transition-[width] duration-700 ease-quint" style={{ width: `${(Math.min(checked, TARGET) / total) * 100}%` }} />
      </div>
      <p className="mt-1 flex gap-4 text-[12px] text-muted" aria-hidden="true">
        <span className="inline-flex items-center gap-1.5"><i className="h-2 w-2 rounded-full bg-cyan" />Found</span>
        <span className="inline-flex items-center gap-1.5"><i className="h-2 w-2 rounded-full bg-yellow" />Edited by you</span>
      </p>
      <p className="mt-3 text-[15px] leading-[1.45]">{message}</p>
      {showLink && (
        <Link href="/onboarding" className="mt-1 inline-flex min-h-11 items-center text-[15px] font-medium underline underline-offset-4">Review my achievements</Link>
      )}
    </div>
  );
}
