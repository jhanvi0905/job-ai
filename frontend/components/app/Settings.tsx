"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/product-api";
import { getSupabase } from "@/lib/supabase/client";
import { EMPTY_PREFS, PrefsForm } from "./PrefsForm";
import { useLoad } from "./hooks";
import { ProfileMeter } from "./retention";
import { Button, Card, QUOTA_LABELS, ErrorNotice, inputClass, PageHeader, Skeleton } from "./ui";

function UsageCard() {
  const q = useLoad(() => api.getUsage());
  if (q.loading) return <Skeleton rows={1} />;
  if (q.error != null || !q.data) return <ErrorNotice error={q.error} onRetry={q.reload} />;
  const u = q.data;
  return (
    <div>
      <p className="text-sm text-slate-700">
        Plan: <span className="font-semibold capitalize">{u.plan}</span> · Credits: <span className="font-semibold">{u.credits}</span>
      </p>
      <ul className="mt-3 space-y-3">
        {Object.keys(u.limits).map((k) => {
          const used = u.used[k] ?? 0;
          const limit = u.limits[k];
          const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
          return (
            <li key={k}>
              <div className="flex justify-between text-sm"><span>{QUOTA_LABELS[k] ?? k} <span className="text-slate-500">(today)</span></span><span className="text-slate-600">{used} / {limit}</span></div>
              <div role="progressbar" aria-label={QUOTA_LABELS[k] ?? k} aria-valuemin={0} aria-valuemax={limit} aria-valuenow={used} className="mt-1.5 h-2 overflow-hidden rounded-full bg-quiet">
                <div className={`h-full rounded-full ${pct >= 90 ? "bg-salmon" : "bg-ink"}`} style={{ width: `${pct}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function DeleteAccount() {
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function del() {
    setBusy(true); setError(null);
    try { await api.deleteMe(); }
    catch (e) { setError(e); setBusy(false); return; }
    // The server already deleted the auth user, so only the local session is cleared.
    try { await getSupabase()?.auth.signOut({ scope: "local" }); } catch { /* cookies may already be gone */ }
    // Hard navigation: resets client state and wins over the SIGNED_OUT -> /login listener.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = "/";
  }
  return (
    <div>
      <p className="text-sm text-slate-700">Permanently delete your account, resume, achievements, matches and tracker. This cannot be undone.</p>
      {!open ? (
        <Button variant="danger" className="mt-3" onClick={() => setOpen(true)}>Delete my account</Button>
      ) : (
        <div className="mt-3 space-y-3" role="group" aria-label="Confirm account deletion">
          <label className="block text-sm">Type <span className="font-mono font-semibold">DELETE</span> to confirm
            <input className={`${inputClass} mt-1`} value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="off" />
          </label>
          <div className="flex gap-2">
            <Button variant="danger" disabled={confirm !== "DELETE" || busy} onClick={del}>{busy ? "Deleting…" : "Permanently delete"}</Button>
            <Button variant="ghost" onClick={() => { setOpen(false); setConfirm(""); }}>Cancel</Button>
          </div>
        </div>
      )}
      {error != null && <div className="mt-3"><ErrorNotice error={error} /></div>}
    </div>
  );
}

function EvidenceCard() {
  const q = useLoad(() => api.getAchievements());
  if (q.loading) return <Skeleton rows={1} />;
  if (q.error != null || !q.data) return <ErrorNotice error={q.error} onRetry={q.reload} />;
  if (q.data.length === 0) {
    return <Card><p className="text-[15px] text-muted">No achievements yet. <Link href="/onboarding" className="font-medium text-ink underline underline-offset-4">Upload your resume</Link> to build your evidence.</p></Card>;
  }
  // The meter is itself a Grovia mini-card, so it stands alone (no card-in-card).
  return <ProfileMeter items={q.data} showLink />;
}

export function Settings() {
  const prefs = useLoad(() => api.getPrefs().catch(() => EMPTY_PREFS));
  return (
    <div className="space-y-6">
      <PageHeader title="Settings" />
      <section aria-label="Your evidence"><EvidenceCard /></section>
      <Card><h2 className="mb-4 font-display text-[22px] leading-[1.25] tracking-[-0.04em] text-ink">Search preferences</h2>
        {prefs.loading ? <Skeleton rows={1} /> : <PrefsForm initial={prefs.data ?? EMPTY_PREFS} />}
      </Card>
      <Card><h2 className="mb-4 font-display text-[22px] leading-[1.25] tracking-[-0.04em] text-ink">Usage and credits</h2><UsageCard /></Card>
      <Card><h2 className="mb-4 font-display text-[22px] leading-[1.25] tracking-[-0.04em] text-alert">Delete account</h2><DeleteAccount /></Card>
    </div>
  );
}
