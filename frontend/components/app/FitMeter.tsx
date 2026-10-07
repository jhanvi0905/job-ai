"use client";

import { useEffect, useState } from "react";
import type { Fit } from "@/lib/product-types";
import { CountUp } from "./CountUp";

const FIT_VALUE: Record<Fit, number> = { strong: 90, plausible: 62, weak: 32, no: 8 };
const FIT_LABEL: Record<Fit, string> = {
  strong: "Strong fit", plausible: "Plausible fit", weak: "Weak fit", no: "Not a fit",
};
const FIT_BAR: Record<Fit, string> = {
  strong: "bg-cyan", plausible: "bg-yellow", weak: "bg-salmon", no: "bg-faint",
};

/**
 * Fit meter (spec §3). The category label is always primary text. With real evidence
 * `counts`, the bar is stacked by requirement: direct (cyan), partial (yellow), gap
 * (salmon), so its colours mean something. Without counts it is a single categorical
 * cue whose length is never shown as a percentage. Pass `value` only for a real score.
 */
export function FitMeter({
  fit, value, label, showValue = false, size = "md", className = "", counts,
}: {
  fit?: Fit | null; value?: number; label?: string; showValue?: boolean;
  size?: "sm" | "md" | "lg"; className?: string;
  /** Real evidence counts from the evaluation. */
  counts?: { strong: number; partial: number; gaps: number };
}) {
  const target = value ?? (fit ? FIT_VALUE[fit] : 0);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(id);
  }, []);
  if (fit == null && value == null) return null;

  const tone: Fit = fit ?? (target >= 75 ? "strong" : target >= 50 ? "plausible" : target >= 25 ? "weak" : "no");
  const text = label ?? FIT_LABEL[tone];
  const h = size === "lg" ? "h-3" : size === "sm" ? "h-1.5" : "h-2";
  const total = counts ? counts.strong + counts.partial + counts.gaps : 0;
  const seg = (n: number) => `${shown && total ? (n / total) * 100 : 0}%`;

  return (
    <div className={className}>
      <div className="flex items-baseline justify-between gap-3 text-[15px]">
        <span className="font-medium text-ink">{text}</span>
        {showValue && value != null && <span className="tabular-nums font-medium text-muted">{Math.round(value)}%</span>}
      </div>
      <div
        role="meter" aria-label="Fit" aria-valuemin={0} aria-valuemax={100}
        aria-valuenow={Math.round(target)} aria-valuetext={showValue && value != null ? `${text}, ${Math.round(value)} percent` : text}
        className={`mt-2 flex gap-0.5 overflow-hidden rounded-full bg-quiet ${h}`}
      >
        {counts && total > 0 ? (
          <>
            <span className="h-full rounded-full bg-cyan transition-[width] duration-1000 ease-quint" style={{ width: seg(counts.strong) }} />
            <span className="h-full rounded-full bg-yellow transition-[width] duration-1000 ease-quint" style={{ width: seg(counts.partial) }} />
            <span className="h-full rounded-full bg-salmon transition-[width] duration-1000 ease-quint" style={{ width: seg(counts.gaps) }} />
          </>
        ) : (
          <span className={`h-full rounded-full transition-[width] duration-1000 ease-quint ${FIT_BAR[tone]}`} style={{ width: shown ? `${target}%` : "0%" }} />
        )}
      </div>
      {counts && (
        <p className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-muted">
          <span className="inline-flex items-center gap-1.5"><i aria-hidden="true" className="h-2 w-2 rounded-full bg-cyan" /><span className="font-medium tabular-nums text-ink"><CountUp value={counts.strong} /></span> strong evidence</span>
          <span className="inline-flex items-center gap-1.5"><i aria-hidden="true" className="h-2 w-2 rounded-full bg-yellow" /><span className="font-medium tabular-nums text-ink"><CountUp value={counts.partial} /></span> partial</span>
          <span className="inline-flex items-center gap-1.5"><i aria-hidden="true" className="h-2 w-2 rounded-full bg-salmon" /><span className="font-medium tabular-nums text-ink"><CountUp value={counts.gaps} /></span> {counts.gaps === 1 ? "gap" : "gaps"}</span>
        </p>
      )}
    </div>
  );
}
