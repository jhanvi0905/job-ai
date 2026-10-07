import Link from "next/link";
import { ApiError } from "@/lib/product-api";

// Grovia system (spec §3): black pill primary (optional arrow chip), ghost pill secondary.
const btn =
  "inline-flex items-center justify-center gap-2 min-h-11 rounded-pill px-5 py-2 text-[15px] font-medium tracking-[-0.03em] transition-[transform,background-color,box-shadow] duration-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink cursor-pointer disabled:cursor-not-allowed disabled:opacity-50";
const variants = {
  primary: "bg-ink text-on-dark shadow-button hover:-translate-y-px",
  secondary: "border border-ink bg-transparent text-ink hover:bg-glass",
  danger: "bg-alert text-on-dark shadow-button hover:-translate-y-px",
  ghost: "text-ink hover:bg-quiet",
} as const;
export type Variant = keyof typeof variants;

export function buttonClass(variant: Variant = "primary", extra = "") {
  return `${btn} ${variants[variant]} ${extra}`;
}

/** 28px arrow chip used inside primary pills. */
export function ArrowChip() {
  return (
    <span aria-hidden="true" className="-mr-3 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-on-dark text-ink">
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
    </span>
  );
}

export function Button({
  variant = "primary", className = "", arrow = false, children, ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; arrow?: boolean }) {
  return (
    <button type="button" {...props} className={buttonClass(variant, className)}>
      {children}{arrow && variant === "primary" && <ArrowChip />}
    </button>
  );
}

export function LinkButton({
  variant = "primary", className = "", arrow = false, children, ...props
}: React.ComponentProps<typeof Link> & { variant?: Variant; arrow?: boolean }) {
  return (
    <Link {...props} className={buttonClass(variant, className)}>
      {children}{arrow && variant === "primary" && <ArrowChip />}
    </Link>
  );
}

export const inputClass =
  "w-full min-h-11 rounded-[14px] border border-line bg-on-dark px-4 py-2 text-[15px] text-ink placeholder:text-faint focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ink";

export function Field({
  label, hint, children,
}: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-slate-800">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2 text-sm text-slate-600">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600" />
      {label}…
    </span>
  );
}

export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div role="status" aria-label="Loading" className="space-y-3">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="rounded-card bg-card p-6 shadow-card">
          <div className="h-4 w-2/5 animate-pulse rounded bg-slate-200" />
          <div className="mt-3 h-3 w-4/5 animate-pulse rounded bg-slate-100" />
          <div className="mt-2 h-3 w-3/5 animate-pulse rounded bg-slate-100" />
        </div>
      ))}
      <span className="sr-only">Loading</span>
    </div>
  );
}

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-card bg-card p-6 shadow-card ${className}`}>
      {children}
    </div>
  );
}

export function PageHeader({
  title, subtitle, action,
}: { title: string; subtitle?: string; action?: React.ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="font-display text-[32px] leading-[1.15] tracking-[-0.05em] text-ink sm:text-[40px]">{title}</h1>
        {subtitle && <p className="mt-2 max-w-[560px] text-base leading-[1.4] text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function EmptyState({
  title, body, action,
}: { title: string; body: string; action?: React.ReactNode }) {
  return (
    <div className="rounded-card bg-glass p-10 text-center">
      <span aria-hidden="true" className="mx-auto mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-highlight text-ink">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
      </span>
      <p className="font-display text-[22px] tracking-[-0.04em] text-ink">{title}</p>
      <p className="mx-auto mt-2 max-w-md text-[15px] leading-[1.45] text-muted">{body}</p>
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

/** Plan quota (429) -> friendly upgrade prompt; anything else -> plain error. */
export function ErrorNotice({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  if (error instanceof ApiError && error.isCredits) {
    return (
      <div role="alert" className="rounded-card bg-highlight p-5 text-[15px] text-ink">
        <p className="font-medium">You&apos;re out of credits for this action.</p>
        <LinkButton href="/settings" variant="primary" className="mt-3">See plan and credits</LinkButton>
      </div>
    );
  }
  if (error instanceof ApiError && error.isRateLimited) {
    const wait = error.retryAfter && error.retryAfter > 0
      ? `Try again in ${error.retryAfter < 90 ? `${error.retryAfter} seconds` : `${Math.ceil(error.retryAfter / 60)} minutes`}.`
      : "Try again in a few seconds.";
    return (
      <div role="alert" className="rounded-card bg-glass p-5 text-[15px] text-ink shadow-soft">
        <p className="font-medium">Slow down a moment.</p>
        <p className="mt-0.5 text-muted">We got a lot of requests at once. {wait} Nothing was lost.</p>
        {onRetry && (
          <button type="button" onClick={onRetry} className="mt-2 inline-flex min-h-11 items-center font-medium underline underline-offset-4">
            Try again
          </button>
        )}
      </div>
    );
  }
  if (error instanceof ApiError && error.isQuota) {
    return (
      <div role="alert" className="rounded-card bg-highlight p-5 text-[15px] text-ink">
        <p className="font-medium">You&apos;ve hit today&apos;s plan limit.</p>
        <p className="mt-1">
          Daily limits reset tomorrow, or Pro raises them.
        </p>
        <LinkButton href="/settings" variant="primary" className="mt-3">
          See plan and usage
        </LinkButton>
      </div>
    );
  }
  const msg = error instanceof Error && error.message ? error.message : "Something went wrong on our side.";
  return (
    <div role="alert" className="rounded-card bg-fit-weak p-5 text-[15px] text-fit-weak-ink">
      <p className="font-medium">That didn&apos;t work.</p>
      <p className="mt-0.5">{msg} Your data is safe.</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="mt-2 inline-flex min-h-11 items-center font-medium underline underline-offset-4">
          Try again
        </button>
      )}
    </div>
  );
}

import type { Fit } from "@/lib/product-types";

// Fit semantics (spec §1): strong = cyan, plausible = yellow, weak = salmon, no = faint. Always labelled.
const fitStyle: Record<Fit, string> = {
  strong: "bg-fit-strong text-fit-strong-ink",
  plausible: "bg-fit-plausible text-fit-plausible-ink",
  weak: "bg-fit-weak text-fit-weak-ink",
  no: "bg-quiet text-muted",
};
const fitLabel: Record<Fit, string> = {
  strong: "Strong fit", plausible: "Plausible fit", weak: "Weak fit", no: "Not a fit",
};

export function FitBadge({ fit }: { fit: Fit | null }) {
  if (!fit) return null;
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${fitStyle[fit]}`}>
      {fitLabel[fit]}
    </span>
  );
}

export const QUOTA_LABELS: Record<string, string> = {
  triage: "Job screenings",
  deep_match: "Deep fit analyses",
  tailor: "Resume tailorings",
  resume_parse: "Resume uploads",
};

export function Chip({ children, tone = "slate" }: { children: React.ReactNode; tone?: "slate" | "indigo" | "emerald" | "amber" }) {
  const t = {
    slate: "bg-quiet text-muted",
    indigo: "bg-highlight text-ink",
    emerald: "bg-fit-strong text-fit-strong-ink",
    amber: "bg-fit-plausible text-fit-plausible-ink",
  }[tone];
  return <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${t}`}>{children}</span>;
}
