import { Odometer } from "./Odometer";
import { ArrowCircle, BookmarkIcon, SampleTag, WandIcon } from "./shared";

type Row = { title: string; company: string; where: string; fit: "Strong fit" | "Plausible" | "Weak fit"; top?: boolean; faded?: boolean };
const ROWS: Row[] = [
  { title: "Data Analyst, Operations", company: "Northwind Co.", where: "Toronto · Hybrid", fit: "Strong fit", top: true },
  { title: "Product Analyst", company: "Harbour Health", where: "Remote, Canada", fit: "Plausible" },
  { title: "BI Developer", company: "Maple Freight", where: "Vancouver", fit: "Weak fit", faded: true },
];
const chip: Record<Row["fit"], string> = {
  "Strong fit": "bg-fit-strong text-fit-strong-ink",
  Plausible: "bg-fit-plausible text-fit-plausible-ink",
  "Weak fit": "bg-fit-weak text-fit-weak-ink",
};

// One bar per requirement of the sample job; segments = your achievements that
// cover it directly (cyan), adjacently (yellow), or a named gap (salmon).
const BARS: Array<{ k: string; full: string; d: number; a: number; g: number }> = [
  { k: "SQL", full: "SQL", d: 3, a: 1, g: 0 },
  { k: "XLS", full: "Excel", d: 2, a: 1, g: 0 },
  { k: "RPT", full: "Reporting", d: 2, a: 1, g: 0 },
  { k: "STK", full: "Stakeholders", d: 1, a: 2, g: 0 },
  { k: "OPS", full: "Process work", d: 1, a: 1, g: 0 },
  { k: "PBI", full: "Power BI", d: 0, a: 0, g: 1.4 },
  { k: "PY", full: "Python", d: 0, a: 0, g: 1.4 },
];
const UNIT = 22;

// Server component: the float-in and bar growth are CSS keyframes (globals.css), so they
// start at first paint without waiting for hydration. Only the Odometer is client JS.
export function HeroCards() {
  return (
    <div className="relative mx-auto w-full max-w-[520px] lg:mx-0 lg:h-[400px] [perspective:1400px]">
      {/* Card A: ranked matches, the top row highlighted like Grovia's list. */}
      <div className="relative lg:absolute lg:left-0 lg:top-0 lg:w-[440px] lg:[transform:rotateY(-7deg)_rotateX(3deg)]">
      <div className="hero-float rounded-[22px] bg-card p-5 shadow-float">
        <div className="flex items-center justify-between">
          <p className="text-lg font-medium text-ink">Your matches</p>
          <div className="flex items-center gap-2">
            <SampleTag />
            <span className="text-sm text-muted">Sort by best fit ⌄</span>
          </div>
        </div>
        <ul className="mt-4 space-y-1">
          {ROWS.map((r) => (
            <li key={r.title}
              className={`flex items-center gap-3 rounded-card px-3 py-3 ${r.top ? "-mx-3 bg-highlight px-6" : ""} ${r.faded ? "opacity-50" : ""}`}>
              <span aria-hidden="true" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-quiet font-display text-sm text-ink">
                {r.company[0]}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[15px] font-medium text-ink">{r.title}</span>
                <span className="block truncate text-[13px] text-muted">{r.company} · {r.where}</span>
              </span>
              <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${chip[r.fit]}`}>{r.fit}</span>
              {r.top && (
                <span className="hidden shrink-0 items-center gap-2 text-ink sm:flex" aria-hidden="true">
                  <BookmarkIcon size={16} /><WandIcon size={16} />
                </span>
              )}
            </li>
          ))}
        </ul>
        <p className="mt-3 inline-flex items-center gap-2 text-sm text-ink">All matches <ArrowCircle size={16} /></p>
      </div>
      </div>

      {/* Card B: the reason for the verdict, overlapping bottom-right. */}
      <div className="relative z-10 -mt-6 ml-auto w-[88%] max-w-[300px] sm:w-[300px] lg:absolute lg:right-[-8px] lg:top-[150px] lg:mt-0 lg:[transform:rotateY(-7deg)_rotateX(3deg)]">
      <div style={{ animationDelay: "0.25s" }} className="hero-float rounded-[22px] border border-on-dark/60 bg-on-dark/70 p-5 shadow-float backdrop-blur-xl">
        <div className="flex items-baseline justify-between gap-2">
          <p className="text-sm text-muted">Why it fits</p>
          <p className="text-[13px] text-muted"><span className="text-alert">2 gaps</span> named</p>
        </div>
        <p className="mt-1 flex items-baseline gap-1.5 font-display text-[30px] leading-none tracking-[-0.04em] text-ink">
          <Odometer value={5} /><span>of 7</span>
          <span className="ml-1 font-sans text-[13px] tracking-[-0.02em] text-muted">requirements</span>
        </p>
        <p className="mt-0.5 text-[12px] text-muted">Sample fit · backed by your evidence</p>
        <ul className="mt-4 flex h-[104px] items-end justify-between gap-2" aria-label="Evidence per requirement (sample)">
          {BARS.map((b, i) => (
            <li key={b.k} className="flex flex-1 flex-col items-center gap-1.5">
              <span className="sr-only">{b.full}: {b.d} direct, {b.a} adjacent{b.g ? ", gap" : ""}</span>
              <span aria-hidden="true" style={{ animationDelay: `${0.7 + i * 0.06}s` }}
                className="hero-bar flex w-full max-w-[22px] origin-bottom flex-col overflow-hidden rounded-[5px]">
                {b.d > 0 && <span className="bg-cyan" style={{ height: b.d * UNIT * 0.9 }} />}
                {b.g > 0 && <span className="bg-salmon" style={{ height: b.g * UNIT * 0.9 }} />}
                {b.a > 0 && <span className="bg-yellow" style={{ height: b.a * UNIT * 0.9 }} />}
              </span>
              <span aria-hidden="true" className="text-[10px] font-medium text-muted">{b.k}</span>
            </li>
          ))}
        </ul>
        <p className="mt-3 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted" aria-hidden="true">
          <span className="inline-flex items-center gap-1"><i className="h-2 w-2 rounded-full bg-cyan" />Direct</span>
          <span className="inline-flex items-center gap-1"><i className="h-2 w-2 rounded-full bg-yellow" />Adjacent</span>
          <span className="inline-flex items-center gap-1"><i className="h-2 w-2 rounded-full bg-salmon" />Gap</span>
        </p>
      </div>
      </div>
    </div>
  );
}
