"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/product-api";
import { APPLICATION_STATUSES, type Application, type ApplicationStatus } from "@/lib/product-types";
import { useLoad } from "./hooks";
import { FollowUpNudge } from "./retention";
import { Button, Card, EmptyState, ErrorNotice, inputClass, LinkButton, PageHeader, Skeleton } from "./ui";

const COL_DOT: Record<ApplicationStatus, string> = {
  saved: "bg-faint", tailored: "bg-yellow", applied: "bg-cyan", interview: "bg-salmon", offer: "bg-ink", rejected: "bg-quiet",
};

function AppCard({ a, onSaved }: { a: Application; onSaved: (a: Application) => void }) {
  const [status, setStatus] = useState<ApplicationStatus>(a.status);
  const [notes, setNotes] = useState(a.notes);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const dirty = status !== a.status || notes !== a.notes;

  async function save() {
    setBusy(true); setError(null);
    try { onSaved(await api.putApplication(a.job_id, status, notes)); }
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  return (
    <Card className="space-y-3 p-4!">
      <Link href={`/jobs/${encodeURIComponent(a.job_id)}`} className="block text-[15px] font-medium leading-snug text-ink hover:underline">
        {a.title ?? "Job"}{a.company ? ` · ${a.company}` : ""}
      </Link>
      <FollowUpNudge a={a} />
      <label className="block text-xs font-medium text-slate-600">
        Status
        <select className={`${inputClass} mt-1`} value={status} onChange={(e) => setStatus(e.target.value as ApplicationStatus)}>
          {APPLICATION_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </label>
      <label className="block text-xs font-medium text-slate-600">
        Notes
        <textarea className={`${inputClass} mt-1`} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      {dirty && <Button className="w-full" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</Button>}
      {error != null && <ErrorNotice error={error} />}
    </Card>
  );
}

export function Tracker() {
  const q = useLoad(() => api.getApplications());
  const [local, setLocal] = useState<Record<string, Application>>({});

  if (q.loading) return <Skeleton />;
  if (q.error != null) return <ErrorNotice error={q.error} onRetry={q.reload} />;
  const apps = (q.data ?? []).map((a) => local[a.job_id] ?? a);

  return (
    <div>
      <PageHeader title="Tracker" subtitle="Where each application stands. Update it yourself; we never apply for you." />
      {apps.length === 0 ? (
        <EmptyState title="Nothing tracked yet" body="Save a job from your feed to start tracking it."
          action={<LinkButton href="/feed" variant="secondary">Go to feed</LinkButton>} />
      ) : (
        <div className="grid gap-4 md:grid-cols-3">
          {APPLICATION_STATUSES.map((s) => {
            const col = apps.filter((a) => a.status === s);
            return (
              <section key={s} aria-labelledby={`col-${s}`} className="space-y-3">
                <h2 id={`col-${s}`} className="flex items-center gap-2 border-b border-line pb-2 font-sans text-[15px] font-medium capitalize text-ink"><i aria-hidden="true" className={`h-2 w-2 rounded-full ${COL_DOT[s]}`} />{s} <span className="font-normal text-muted">{col.length}</span></h2>
                {col.map((a) => (
                  <AppCard key={`${a.job_id}-${a.status}`} a={a} onSaved={(n) => setLocal((m) => ({ ...m, [n.job_id]: n }))} />
                ))}
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
