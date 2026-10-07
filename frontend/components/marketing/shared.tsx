import Link from "next/link";

export const CTA_LABEL = "Get my free fit check";
/** Friction remover under primary CTAs: cost, commitment, control. */
export const FRICTION_LINE = "Free to start · No card · We never apply for you";
export const TRUST_LINES = ["No card required", "You approve every change", "Delete your data anytime"];

/** Grovia content width: 1040px with a 16px gutter. */
export function Container({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`mx-auto w-full max-w-[1072px] px-4 ${className}`}>{children}</div>;
}

export function H2({ id, children, className = "", onDark = false }: {
  id?: string; children: React.ReactNode; className?: string; onDark?: boolean;
}) {
  return (
    <h2 id={id} className={`font-display text-[32px] leading-[1.15] tracking-[-0.05em] sm:text-[40px] ${onDark ? "text-on-dark" : "text-ink"} ${className}`}>
      {children}
    </h2>
  );
}

export function Lead({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <p className={`text-lg leading-[1.4] tracking-[-0.03em] text-muted ${className}`}>{children}</p>;
}

const pillBase =
  "inline-flex h-11 shrink-0 items-center gap-3 rounded-pill text-base font-medium tracking-[-0.03em] transition-[transform,box-shadow,background-color] duration-200 hover:-translate-y-px focus-visible:outline-2 focus-visible:outline-offset-2 cursor-pointer disabled:cursor-not-allowed disabled:opacity-60";

const pillTone = {
  black: "bg-ink text-on-dark shadow-button py-2 pl-4 pr-2",
  yellow: "bg-highlight text-ink shadow-button py-2 pl-4 pr-2",
  ghost: "border border-ink text-ink px-5 hover:bg-glass",
  ghostLight: "border border-on-dark/70 text-on-dark px-5 hover:bg-on-dark-fill",
} as const;
export type PillTone = keyof typeof pillTone;

export function pillClass(tone: PillTone = "black", extra = "") {
  return `${pillBase} ${pillTone[tone]} ${extra}`;
}

/** 28px arrow chip: white on black buttons, black on yellow. */
export function ArrowChip({ tone = "black" }: { tone?: PillTone }) {
  const c = tone === "yellow" ? "bg-ink text-on-dark" : "bg-on-dark text-ink";
  return (
    <span aria-hidden="true" className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${c}`}>
      <Arrow size={14} />
    </span>
  );
}

/** Grovia pill CTA: label + arrow chip for black/yellow, plain label for ghost. */
export function Pill({
  href = "/signup", tone = "black", children = CTA_LABEL, className = "",
}: { href?: string; tone?: PillTone; children?: React.ReactNode; className?: string }) {
  const chip = tone === "black" || tone === "yellow";
  return (
    <Link href={href} className={pillClass(tone, className)}>
      {children}
      {chip && <ArrowChip tone={tone} />}
    </Link>
  );
}

export function SampleTag({ className = "", onDark = false }: { className?: string; onDark?: boolean }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium uppercase tracking-[0.04em] ${onDark ? "bg-on-dark-fill text-on-dark" : "bg-quiet text-muted"} ${className}`}>
      Sample
    </span>
  );
}

export function TrustLines({ onDark = false, className = "" }: { onDark?: boolean; className?: string }) {
  return (
    <ul className={`flex flex-col gap-2 text-[15px] ${onDark ? "text-on-dark-muted" : "text-muted"} ${className}`}>
      {TRUST_LINES.map((t) => (
        <li key={t} className="flex items-center gap-2.5">
          <CheckIcon size={16} className={onDark ? "text-on-dark" : "text-ink"} />
          {t}
        </li>
      ))}
    </ul>
  );
}

type IconProps = { className?: string; size?: number };
const svg = (size = 18) => ({
  viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8,
  strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true, width: size, height: size,
});
export const Arrow = ({ className = "", size }: IconProps) => <svg {...svg(size)} className={className}><path d="M5 12h14M13 6l6 6-6 6" /></svg>;
export const CheckIcon = ({ className = "", size }: IconProps) => <svg {...svg(size)} className={className}><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>;
export const PencilIcon = ({ className = "", size }: IconProps) => <svg {...svg(size)} className={className}><path d="M4 20h4L19 9l-4-4L4 16v4zM13.5 6.5l4 4" /></svg>;
export const BookmarkIcon = ({ className = "", size }: IconProps) => <svg {...svg(size)} className={className}><path d="M6 4h12v16l-6-4-6 4z" /></svg>;
export const SparkIcon = ({ className = "", size }: IconProps) => <svg {...svg(size)} className={className}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6" /></svg>;
export const LinkIcon = ({ className = "", size }: IconProps) => <svg {...svg(size)} className={className}><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></svg>;
export const GaugeIcon = ({ className = "", size }: IconProps) => <svg {...svg(size)} className={className}><path d="M4 16a8 8 0 1 1 16 0M12 16l4-5" /></svg>;
export const StackIcon = ({ className = "", size }: IconProps) => <svg {...svg(size)} className={className}><path d="m12 4 8 4-8 4-8-4 8-4zM4 12l8 4 8-4M4 16l8 4 8-4" /></svg>;
export const WandIcon = ({ className = "", size }: IconProps) => <svg {...svg(size)} className={className}><path d="M4 20 15 9M14 4v2M18 6l-1.5 1.5M20 10h-2M12.5 7.5l4 4" /></svg>;
export const ColumnsIcon = ({ className = "", size }: IconProps) => <svg {...svg(size)} className={className}><rect x="4" y="4" width="4.5" height="16" rx="1" /><rect x="10" y="4" width="4.5" height="10" rx="1" /><rect x="16" y="4" width="4" height="13" rx="1" /></svg>;
export const ArrowCircle = ({ className = "", size }: IconProps) => <svg {...svg(size)} className={className}><circle cx="12" cy="12" r="9" /><path d="M8 12h8M13 9l3 3-3 3" /></svg>;
