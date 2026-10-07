"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, api } from "@/lib/product-api";
import type { Achievement, ResumeParseResult } from "@/lib/product-types";
import { AchievementList } from "./AchievementList";
import { EMPTY_PREFS, PrefsForm } from "./PrefsForm";
import { useLoad } from "./hooks";
import { ProfileMeter } from "./retention";
import { usePersistentTask } from "./useTask";

const PARSE_TASK_KEY = "fitwise:task:resume_parse";
import { Button, Card, ErrorNotice, PageHeader, Skeleton, Spinner } from "./ui";

const STEPS = ["Upload resume", "Check achievements", "Your preferences"];

function Stepper({ step }: { step: number }) {
  return (
    <nav aria-label="Setup progress">
      <p className="text-sm font-medium text-slate-600">
        Step {step} of {STEPS.length}: <span className="text-slate-900">{STEPS[step - 1]}</span>
      </p>
      <div
        role="progressbar" aria-label="Setup progress" aria-valuemin={1} aria-valuemax={STEPS.length}
        aria-valuenow={step} aria-valuetext={`Step ${step} of ${STEPS.length}`}
        className="mt-2 h-2 overflow-hidden rounded-full bg-slate-200"
      >
        <div className="h-full rounded-full bg-indigo-600 transition-[width] duration-500" style={{ width: `${(step / STEPS.length) * 100}%` }} />
      </div>
      <ol className="mt-3 grid grid-cols-3 gap-2 text-xs sm:text-sm">
        {STEPS.map((t, i) => {
          const n = i + 1;
          const done = n < step, active = n === step;
          return (
            <li key={t} aria-current={active ? "step" : undefined}
              className={`flex items-center gap-2 ${active ? "font-medium text-ink" : done ? "text-slate-700" : "text-slate-500"}`}>
              <span aria-hidden="true" className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${done ? "bg-emerald-600 text-white" : active ? "bg-indigo-600 text-white" : "bg-slate-200 text-slate-600"}`}>
                {done ? "✓" : n}
              </span>
              <span>{t}{done && <span className="sr-only"> (done)</span>}</span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export function Onboarding() {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const existing = useLoad(() => api.getAchievements().catch(() => [] as Achievement[]));
  const prefs = useLoad(() => api.getPrefs().catch(() => EMPTY_PREFS));
  const [uploaded, setUploaded] = useState<Achievement[] | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [celebrate, setCelebrate] = useState(false);
  const [saved, setSaved] = useState(false);
  const lastFile = useRef<File | null>(null);

  // Upload returns 201 + task id; achievements are parsed in the background.
  const parse = usePersistentTask<ResumeParseResult>(PARSE_TASK_KEY, async (t) => {
    if (t.status !== "succeeded") return;
    try {
      setUploaded(await api.getAchievements());
      setCelebrate(true);
    } catch (e) { setError(e); }
  });
  const busy = uploading || parse.active;

  const achievements = uploaded ?? existing.data;
  const hasAch = !!achievements && achievements.length > 0;
  const step = !hasAch ? 1 : 2;

  useEffect(() => {
    if (!celebrate) return;
    const t = setTimeout(() => setCelebrate(false), 6000);
    return () => clearTimeout(t);
  }, [celebrate]);

  async function upload(file: File) {
    lastFile.current = file;
    setUploading(true); setError(null); setCelebrate(false);
    try {
      const res = await api.uploadResume(file);
      parse.start(res.task_id);
    } catch (err) { setError(err); } finally { setUploading(false); }
  }

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) void upload(file);
  }

  /** Retry a failed parse: re-send the same file if we still have it, else pick again. */
  function retryParse() {
    parse.clear();
    if (lastFile.current) void upload(lastFile.current);
    else fileRef.current?.click();
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title="Let's find your first matches"
        subtitle="Three quick steps. Upload your resume, check what we found, and tell us what you want. Then your first matches are ready."
      />
      <Stepper step={step === 2 && saved ? 3 : step} />

      <div role="status" aria-live="polite">
        {celebrate && (
          <div className="pop-in rounded-card bg-highlight p-5 text-ink shadow-float">
            <p className="font-display text-[22px] tracking-[-0.04em]">
              <span aria-hidden="true">&#10024; </span>We found {achievements?.length ?? 0} achievements in your resume.
            </p>
            <p className="mt-1 text-sm">That is your evidence base. Next, check each one. Fix anything we got wrong and remove what you would not defend in an interview.</p>
          </div>
        )}
      </div>

      <Card>
        <h2 className="font-display text-[22px] leading-[1.25] tracking-[-0.04em] text-ink">1. Your resume</h2>
        <p className="mt-1 text-sm text-slate-600">PDF or DOCX. We pull out your real achievements. Nothing is matched until you have checked them. You can delete everything any time in Settings.</p>
        <input ref={fileRef} type="file" accept=".pdf,.docx,.doc,.txt" className="sr-only" aria-label="Resume file" onChange={onFile} />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button onClick={() => fileRef.current?.click()} disabled={busy}>
            {hasAch ? "Replace my resume" : "Choose my resume"}
          </Button>
          {uploading && <Spinner label="Uploading" />}
          {!uploading && parse.active && (
            <Spinner label={parse.task?.status === "running" ? "Reading your resume" : "Reading your resume (queued)"} />
          )}
        </div>
        {!uploading && parse.active && (
          <p className="mt-2 text-sm text-muted">This usually takes under a minute. You can stay here; your achievements appear below when they&apos;re ready.</p>
        )}
        {parse.task?.status === "failed" && (
          <div className="mt-3">
            <ErrorNotice
              error={new Error(parse.task.error ? `We couldn't read that resume: ${parse.task.error}.` : "We couldn't read that resume.")}
              onRetry={retryParse} />
          </div>
        )}
        {parse.pollError != null && <div className="mt-3"><ErrorNotice error={parse.pollError}
          onRetry={parse.pollError instanceof ApiError && parse.pollError.status === 404 ? retryParse : parse.retryPolling} /></div>}
        {error != null && <div className="mt-3"><ErrorNotice error={error} onRetry={retryParse} /></div>}
      </Card>

      <Card>
        <h2 className="font-display text-[22px] leading-[1.25] tracking-[-0.04em] text-ink">2. Check your achievements</h2>
        <p className="mt-1 mb-3 text-sm text-slate-600">This is your story, so edit it. Everything we match and rewrite comes from here and nowhere else.</p>
        {busy && !uploading ? <Skeleton rows={2} /> : existing.loading && !uploaded ? <Skeleton rows={2} /> :
          hasAch ? (
            <div className="space-y-3">
              <ProfileMeter items={achievements} />
              <AchievementList items={achievements} onChange={setUploaded} />
            </div>
          ) : (
            <p className="text-sm text-slate-600">Nothing here yet. Upload your resume above and your achievements will appear for you to check.</p>
          )}
      </Card>

      <Card>
        <h2 className="font-display text-[22px] leading-[1.25] tracking-[-0.04em] text-ink">3. What are you looking for?</h2>
        <p className="mt-1 text-sm text-slate-600">Last step. This keeps jobs you would never take out of your feed.</p>
        <div className="mt-4">
          {prefs.loading ? <Skeleton rows={1} /> : (
            <PrefsForm initial={prefs.data ?? EMPTY_PREFS} submitLabel="Save and show my matches" onSaved={() => { setSaved(true); router.push("/feed"); }} />
          )}
        </div>
      </Card>
    </div>
  );
}
