"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/product-api";
import type { TailorRun } from "@/lib/product-types";
import { Button, Card, Chip, EmptyState, ErrorNotice, PageHeader, Spinner } from "./ui";

export function TailorView() {
  const { id } = useParams<{ id: string }>();
  const [run, setRun] = useState<TailorRun | null>(null);
  const [accepted, setAccepted] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState<"gen" | "save" | "dl" | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [savedNote, setSavedNote] = useState(false);

  async function generate() {
    setBusy("gen"); setError(null); setSavedNote(false);
    try {
      const r = await api.tailorJob(id);
      setRun(r); setAccepted(new Set());
    } catch (e) { setError(e); } finally { setBusy(null); }
  }
  const toggle = (i: number) => {
    setSavedNote(false);
    setAccepted((s) => { const n = new Set(s); if (n.has(i)) n.delete(i); else n.add(i); return n; });
  };
  async function save() {
    if (!run) return;
    setBusy("save"); setError(null);
    try { await api.acceptTailor(run.run_id, [...accepted].sort((a, b) => a - b)); setSavedNote(true); }
    catch (e) { setError(e); } finally { setBusy(null); }
  }
  async function download() {
    if (!run) return;
    setBusy("dl"); setError(null);
    try {
      const blob = await api.downloadTailor(run.run_id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "tailored-resume.docx"; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { setError(e); } finally { setBusy(null); }
  }

  return (
    <div className="space-y-6">
      <Link href={`/jobs/${encodeURIComponent(id)}`} className="text-sm font-medium text-slate-600 hover:text-slate-900">&larr; Back to job</Link>
      <PageHeader title="Tailor your resume" subtitle="Every proposed bullet cites the achievements it is based on. Accept only what is true." />
      {!run ? (
        <EmptyState title="Ready to tailor this resume?"
          body="We reword your existing bullets to match this job's language. Nothing is added that your resume does not support."
          action={<Button onClick={generate} disabled={busy === "gen"}>{busy === "gen" ? "Rewriting from your evidence…" : "Suggest tailored bullets"}</Button>} />
      ) : run.bullets.length === 0 ? (
        <EmptyState title="No rewrites suggested" body="Either your bullets already speak this job's language, or we didn't have enough evidence to reword safely. We would rather suggest nothing than invent something." />
      ) : (
        <>
          <ul className="space-y-4">
            {run.bullets.map((p, i) => (
              <li key={i}>
                <Card>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div><p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Before</p><p className="mt-1 text-sm text-slate-700">{p.original}</p></div>
                    <div><p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">After</p><p className="mt-1 text-sm text-slate-900">{p.proposed}</p></div>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
                      Based on: {p.evidence_ids.length ? p.evidence_ids.map((e) => <Chip key={String(e)} tone="indigo">Achievement #{e}</Chip>) : "no citation"}
                    </div>
                    <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
                      <input type="checkbox" className="h-4 w-4 accent-indigo-600" checked={accepted.has(i)} onChange={() => toggle(i)} />
                      Accept this change
                    </label>
                  </div>
                </Card>
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={save} disabled={busy !== null}>{busy === "save" ? "Saving…" : `Save ${accepted.size} accepted`}</Button>
            <Button variant="secondary" onClick={download} disabled={busy !== null}>{busy === "dl" ? "Preparing…" : "Download DOCX"}</Button>
            {savedNote && <span role="status" className="text-sm text-emerald-700">Saved. Download to get the updated file.</span>}
          </div>
        </>
      )}
      {busy === "gen" && <Spinner label="Writing suggestions" />}
      {error != null && <ErrorNotice error={error} />}
    </div>
  );
}
