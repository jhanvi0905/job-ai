"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/product-api";
import type { Application, ApplicationStatus, FeedItem, RefreshSummary, TaskStatus } from "@/lib/product-types";
import { useLoad } from "./hooks";
import { usePersistentTask } from "./useTask";
import { FitMeter } from "./FitMeter";
import { NewMatchBadge, ThisWeekCard, newMatchInfo, useLastVisit } from "./retention";
import {
  Button, Card, EmptyState, ErrorNotice, FitBadge, LinkButton, PageHeader, Skeleton, Spinner,
} from "./ui";

type MinFit = "all" | "plausible" | "strong";
const REFRESH_TASK_KEY = "fitwise:task:feed_refresh";
const FILTERS: Array<{ key: MinFit; label: string }> = [
  { key: "all", label: "All" },
  { key: "plausible", label: "Plausible or better" },
  { key: "strong", label: "Strong only" },
];

/** Label for a feed item already in the tracker past "saved": never downgrade it. */
const TRACKED_LABEL: Record<Exclude<ApplicationStatus, "saved">, string> = {
  tailored: "Already tailored",
  applied: "Already applied",
  interview: "Interviewing",
  offer: "Offer received",
  rejected: "Closed in tracker",
};

function JobCard({ item, isNew = false, highlight = false, trackedStatus = null }: {
  item: FeedItem; isNew?: boolean; highlight?: boolean; trackedStatus?: ApplicationStatus | null;
}) {
  // Local status wins once the user acts on this card; otherwise use what /applications said.
  const [localStatus, setLocalStatus] = useState<ApplicationStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const status = localStatus ?? trackedStatus;

  async function save() {
    setErr(null); setBusy(true);
    try {
      // Re-check the tracker first: the list may be stale (another tab, the job page).
      // Saving over "applied"/"interview"/... would silently downgrade it.
      const existing = (await api.getApplications()).find((a) => a.job_id === item.job_id);
      if (existing) { setLocalStatus(existing.status); return; }
      const res = await api.putApplication(item.job_id, "saved", "");
      setLocalStatus(res?.status ?? "saved");
    } catch (e) { setErr(e); }
    finally { setBusy(false); }
  }
  const saveLabel = !status ? (busy ? "Saving…" : "Save") : status === "saved" ? "Saved" : TRACKED_LABEL[status];
  return (
    <Card className={highlight ? "bg-highlight!" : ""}>
      {highlight && <p className="mb-2 text-[13px] font-medium text-ink">Today&apos;s best fit for you</p>}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-display text-[22px] leading-[1.25] tracking-[-0.04em] text-ink">
            <Link href={`/jobs/${encodeURIComponent(item.job_id)}`} className="hover:underline">{item.title}</Link>
          </h3>
          <p className="text-sm text-slate-600">
            {item.company}
            {item.location ? ` · ${item.location}` : ""}
            {item.workplace_type ? ` · ${item.workplace_type}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isNew && <span className="rounded-full bg-on-dark px-2.5 py-1 text-xs font-medium text-ink shadow-float">New since last visit</span>}
          <FitBadge fit={item.fit} />
        </div>
      </div>
      {item.fit && <FitMeter fit={item.fit} size="sm" className="mt-3 max-w-xs" label="How well your experience covers this job" />}
      {item.why_fits && <p className="mt-3 text-sm text-slate-800"><span className="font-medium">Why it fits: </span>{item.why_fits}</p>}
      {item.gaps.length > 0 && (
        <p className="mt-2 text-sm text-slate-600"><span className="font-medium">Honest gaps: </span>{item.gaps.join("; ")}</p>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <LinkButton href={`/jobs/${encodeURIComponent(item.job_id)}`} variant="primary" arrow>Open job</LinkButton>
        <Button variant="secondary" onClick={save} disabled={busy || status !== null}>{saveLabel}</Button>
        {status && status !== "saved" && (
          <Link href="/tracker" className="inline-flex min-h-11 items-center px-2 text-sm text-muted underline underline-offset-4 hover:text-ink">View in tracker</Link>
        )}
      </div>
      {err != null && <div className="mt-3"><ErrorNotice error={err} onRetry={save} /></div>}
    </Card>
  );
}

const SUMMARY_ROWS: Array<[keyof RefreshSummary, string]> = [
  ["considered", "Considered"], ["cached", "Already scored"], ["filtered", "Filtered out"], ["rejected", "Rejected"],
  ["triaged", "Triaged"], ["matched", "Matched"], ["deferred", "Deferred"], ["errored", "Errors"],
];

function Summary({ s, onDismiss }: { s: Partial<RefreshSummary>; onDismiss: () => void }) {
  return (
    <div role="status" className="rounded-card bg-card p-5 text-[15px] text-ink shadow-float">
      <div className="flex items-start justify-between gap-3">
        <p className="font-medium">Done. Here is what we checked for you.</p>
        <button type="button" onClick={onDismiss} className="-mr-2 -mt-2 inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-muted hover:bg-quiet hover:text-ink">
          <span className="sr-only">Dismiss summary</span>
          <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M6 6l12 12M18 6 6 18" /></svg>
        </button>
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-4">
        {SUMMARY_ROWS.map(([k, label]) => (
          <div key={k} className="flex justify-between gap-2"><dt className="text-muted">{label}</dt><dd className="font-medium tabular-nums">{typeof s[k] === "number" ? s[k] : 0}</dd></div>
        ))}
      </dl>
    </div>
  );
}

/** Queued / running progress for a feed refresh task. */
function RefreshProgress({ status }: { status: TaskStatus | undefined }) {
  const running = status === "running";
  return (
    <div className="rounded-card bg-card p-5 shadow-float">
      <Spinner label={running
        ? "Looking for new jobs and scoring them against your resume. This can take a minute"
        : "Queued. Your refresh starts in a moment"} />
      <p className="mt-2 text-sm text-muted">You can leave this page; we&apos;ll keep working and show the results when you&apos;re back.</p>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-quiet" aria-hidden="true">
        <div className={`h-full animate-pulse rounded-full bg-ink transition-[width] duration-700 ${running ? "w-2/3" : "w-1/6"}`} />
      </div>
    </div>
  );
}

function FeedList({ minFit, newIds, tracked, onItems }: {
  minFit: MinFit; newIds: Set<number>; tracked: Map<number, ApplicationStatus> | null; onItems?: (items: FeedItem[]) => void;
}) {
  const feed = useLoad(() => api.getFeed({ limit: 100, min_fit: minFit === "all" ? undefined : minFit })
    .then((f) => { if (minFit === "all") onItems?.(f.items); return f; }));
  if (feed.loading) return <Skeleton />;
  if (feed.error != null) return <ErrorNotice error={feed.error} onRetry={feed.reload} />;
  const items = feed.data?.items ?? [];
  if (items.length === 0) {
    return minFit === "all" ? (
      <EmptyState title="Your first matches are one refresh away"
        body="We haven't looked for jobs for you yet. Check your resume and search preferences, then press Refresh matches. We only keep jobs you could honestly apply to."
        action={<LinkButton href="/onboarding" variant="secondary">Review my profile</LinkButton>} />
    ) : (
      <EmptyState title="Nothing at this fit level right now" body="That can be a good sign: we would rather show fewer jobs than pad the list. Try a broader filter to see the rest." />
    );
  }
  // Top-ranked strong fit you haven't saved yet gets the highlight row (spec §3).
  const topId = tracked ? items.find((i) => i.fit === "strong" && !tracked.has(i.job_id))?.job_id : undefined;
  return (
    <ul className="space-y-4">
      {items.map((i) => (
        <li key={i.job_id}>
          <JobCard item={i} isNew={newIds.has(i.job_id)} highlight={i.job_id === topId} trackedStatus={tracked?.get(i.job_id) ?? null} />
        </li>
      ))}
    </ul>
  );
}

export function Feed() {
  const [filter, setFilter] = useState<MinFit>("all");
  const [version, setVersion] = useState(0);
  const [starting, setStarting] = useState(false);
  const [refreshError, setRefreshError] = useState<unknown>(null);
  const [summaryHidden, setSummaryHidden] = useState(false);
  // Retention (UI-only): items from the unfiltered list + tracker rows the API already returns.
  const [allItems, setAllItems] = useState<FeedItem[] | null>(null);
  const apps = useLoad<Application[] | null>(() => api.getApplications().catch(() => null));
  const lastVisit = useLastVisit();
  const info = newMatchInfo(allItems ?? [], lastVisit, apps.data);
  const tracked = apps.data ? new Map(apps.data.map((a) => [a.job_id, a.status] as const)) : null;

  // Background refresh (202 + task id). The id survives a reload via sessionStorage.
  const job = usePersistentTask<RefreshSummary>(REFRESH_TASK_KEY, (t) => {
    if (t.status === "succeeded") setVersion((v) => v + 1);
  });
  const refreshing = starting || job.active;
  const task = job.task;

  async function refresh() {
    setStarting(true); setRefreshError(null); setSummaryHidden(false);
    job.clear(); // drop any settled/lost task; the POST returns the active one if still running
    try {
      const accepted = await api.refreshFeed();
      job.start(accepted.task_id);
    } catch (e) { setRefreshError(e); }
    finally { setStarting(false); }
  }

  return (
    <div>
      <PageHeader
        title="Your matches"
        subtitle="Fewer jobs, better ones. Ranked by how well your real experience covers each requirement."
        action={<Button onClick={refresh} disabled={refreshing} arrow>{refreshing ? "Refreshing…" : "Refresh matches"}</Button>}
      />
      <div className="grid items-start gap-8 lg:grid-cols-[1fr_320px]">
      <div className="min-w-0">
      <div className="mb-5 space-y-3 empty:hidden">
        {allItems && <NewMatchBadge info={info} />}
        {refreshing && <RefreshProgress status={task?.status} />}
        {task?.status === "succeeded" && !summaryHidden && (
          <Summary s={task.result ?? {}} onDismiss={() => { setSummaryHidden(true); job.clear(); }} />
        )}
        {task?.status === "failed" && (
          <ErrorNotice error={new Error(task.error ? `The refresh stopped: ${task.error}.` : "The refresh stopped before it finished.")} onRetry={refresh} />
        )}
        {job.pollError != null && <ErrorNotice error={job.pollError} onRetry={refresh} />}
        {refreshError != null && <ErrorNotice error={refreshError} onRetry={refresh} />}
      </div>
      <div role="group" aria-label="Filter by fit" className="mb-5 grid grid-cols-3 gap-1 rounded-[40px] bg-quiet p-1.5">
        {FILTERS.map((f) => (
          <button key={f.key} type="button" aria-pressed={filter === f.key} onClick={() => setFilter(f.key)}
            className={`inline-flex min-h-11 items-center justify-center rounded-pill px-3 text-[14px] font-medium focus-visible:outline-2 focus-visible:outline-ink sm:text-[15px] ${filter === f.key ? "bg-on-dark text-ink shadow-soft" : "text-muted hover:text-ink"}`}>
            {f.label}
          </button>
        ))}
      </div>
      <FeedList key={`${filter}-${version}`} minFit={filter} newIds={info.ids}
        tracked={tracked} onItems={setAllItems} />
      </div>
      <aside className="space-y-4 lg:sticky lg:top-28" aria-label="Your progress">
        <ThisWeekCard apps={apps.loading ? null : apps.data} />
      </aside>
      </div>
    </div>
  );
}
