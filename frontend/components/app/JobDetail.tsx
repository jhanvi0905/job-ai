"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/product-api";
import { useLoad } from "./hooks";
import { FitMeter } from "./FitMeter";
import { ArrowChip, Button, buttonClass, Card, Chip, ErrorNotice, FitBadge, LinkButton, PageHeader, Skeleton } from "./ui";

const strTone = { strong: "emerald", plausible: "amber", weak: "slate" } as const;

function EvCol({ title, items, tone }: { title: string; items: string[]; tone?: "emerald" | "amber" }) {
  const dot = tone === "emerald" ? "bg-cyan" : tone === "amber" ? "bg-yellow" : "bg-faint";
  return (
    <div className="rounded-card bg-card p-5 shadow-card">
      <h3 className="flex items-center gap-2 text-[15px] font-medium text-ink"><i aria-hidden="true" className={`h-2 w-2 rounded-full ${dot}`} />{title}</h3>
      {items.length ? (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">{items.map((r, i) => <li key={i}>{r}</li>)}</ul>
      ) : <p className="mt-2 text-sm text-slate-500">None found.</p>}
    </div>
  );
}

export function JobDetailView() {
  const { id } = useParams<{ id: string }>();
  const q = useLoad(() => api.getJob(id));
  const [analysing, setAnalysing] = useState(false);
  const [aErr, setAErr] = useState<unknown>(null);

  async function analyse() {
    setAnalysing(true); setAErr(null);
    try { await api.analyseJob(id); q.reload(); } catch (e) { setAErr(e); } finally { setAnalysing(false); }
  }

  if (q.loading) return <Skeleton />;
  if (q.error != null || !q.data) return <ErrorNotice error={q.error} onRetry={q.reload} />;
  const { job, evaluation } = q.data;

  return (
    <div className="space-y-6">
      <Link href="/feed" className="inline-flex min-h-11 items-center text-[15px] text-muted hover:text-ink">&larr; Back to matches</Link>
      <PageHeader
        title={job.title}
        subtitle={[job.company, job.location, job.workplace_type].filter(Boolean).join(" · ")}
        action={evaluation ? <FitBadge fit={evaluation.fit} /> : undefined}
      />
      {evaluation?.fit && (
        <Card><FitMeter fit={evaluation.fit} size="lg" label="Your fit for this job"
          counts={{ strong: evaluation.strong_evidence.length, partial: evaluation.partial_evidence.length, gaps: evaluation.gaps.length }} />
          <p className="mt-2 text-xs text-slate-500">Based only on what your resume can prove, requirement by requirement. Gaps are shown below, not hidden.</p></Card>
      )}
      <div className="flex flex-wrap gap-2">
        <a href={job.apply_url} target="_blank" rel="noopener noreferrer"
          className={buttonClass("primary")}>
          Apply on employer site<span className="sr-only"> (opens in a new tab)</span><ArrowChip />
        </a>
        <LinkButton href={`/jobs/${encodeURIComponent(id)}/tailor`} variant="secondary">Tailor my resume</LinkButton>
      </div>

      {!evaluation ? (
        <Card>
          <p className="text-sm text-slate-700">We haven&apos;t checked this job against your experience yet. It takes a moment and shows you exactly where you match and where you don&apos;t.</p>
          <Button className="mt-3" onClick={analyse} disabled={analysing}>{analysing ? "Checking against your experience…" : "Check my fit"}</Button>
          {aErr != null && <div className="mt-3"><ErrorNotice error={aErr} /></div>}
        </Card>
      ) : (
        <>
          {evaluation.reason && <Card><h2 className="font-display text-[22px] leading-[1.25] tracking-[-0.04em] text-ink">Why it fits</h2><p className="mt-1 text-sm text-slate-700">{evaluation.reason}</p></Card>}
          <section aria-labelledby="req" className="grid gap-4 md:grid-cols-3">
            <h2 id="req" className="sr-only">Requirements versus your evidence</h2>
            <EvCol title="What the job asks for" items={evaluation.requirements} />
            <EvCol title="Strong evidence from your resume" items={evaluation.strong_evidence} tone="emerald" />
            <EvCol title="Partial evidence" items={evaluation.partial_evidence} tone="amber" />
          </section>
          {evaluation.matched_achievements.length > 0 && (
            <Card>
              <h2 className="font-display text-[22px] leading-[1.25] tracking-[-0.04em] text-ink">Achievements we matched</h2>
              <ul className="mt-2 space-y-2 text-sm">
                {evaluation.matched_achievements.map((m) => (
                  <li key={m.id} className="flex flex-wrap items-center gap-2">
                    <Chip tone={strTone[m.strength]}>{m.strength}</Chip>
                    <span className="text-slate-500">#{m.id}</span>
                    <span className="text-slate-700">{m.supports.join("; ")}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
          {evaluation.gaps.length > 0 && (
            <Card>
              <h2 className="font-display text-[22px] leading-[1.25] tracking-[-0.04em] text-ink">Honest gaps: what the job asks for that your resume doesn&apos;t show</h2>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">{evaluation.gaps.map((g, i) => <li key={i}>{g}</li>)}</ul>
            </Card>
          )}
        </>
      )}

      <Card>
        <h2 className="font-display text-[22px] leading-[1.25] tracking-[-0.04em] text-ink">Job description</h2>
        <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{job.description}</p>
      </Card>
    </div>
  );
}
