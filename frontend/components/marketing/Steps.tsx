"use client";

import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { Appear, EASE } from "./motion";
import { CheckIcon, Container, LinkIcon, PencilIcon } from "./shared";

function VisualFrame({ children, tint }: { children: React.ReactNode; tint: string }) {
  return (
    <div className="relative h-full min-h-[220px] overflow-hidden rounded-[16px] p-3" style={{ background: tint }}>
      <div className="h-full rounded-[12px] bg-card p-3 shadow-float">{children}</div>
    </div>
  );
}

const V1 = () => (
  <VisualFrame tint="linear-gradient(160deg, var(--chart-cyan), var(--highlight) 55%, var(--chart-salmon))">
    <p className="text-[12px] font-medium text-ink">Your achievements</p>
    <p className="text-[11px] text-muted">Found in your resume · edit any</p>
    <ul className="mt-3 space-y-2">
      {["Cut reporting from 6h to 1h", "Ran the monthly ops review", "Cleaned 3 years of data"].map((t) => (
        <li key={t} className="flex items-center justify-between gap-2 rounded-[10px] bg-quiet px-2.5 py-2 text-[12px] text-ink">
          <span className="truncate">{t}</span><PencilIcon size={13} className="shrink-0 text-muted" />
        </li>
      ))}
    </ul>
  </VisualFrame>
);

const REQS: Array<[string, "Direct" | "Adjacent" | "Gap"]> = [["SQL", "Direct"], ["Excel reporting", "Direct"], ["Stakeholder updates", "Adjacent"], ["Power BI", "Gap"]];
const reqTone = { Direct: "bg-fit-strong text-fit-strong-ink", Adjacent: "bg-fit-plausible text-fit-plausible-ink", Gap: "bg-fit-weak text-fit-weak-ink" };
const V2 = () => (
  <VisualFrame tint="linear-gradient(160deg, var(--highlight), var(--chart-yellow) 50%, var(--chart-salmon))">
    <p className="text-[12px] font-medium text-ink">Requirements</p>
    <ul className="mt-3 space-y-2">
      {REQS.map(([r, t]) => (
        <li key={r} className="flex items-center justify-between gap-2 text-[12px] text-ink">
          <span className="flex items-center gap-1.5">
            {t === "Gap" ? <span aria-hidden="true" className="h-3.5 w-3.5 rounded-full border border-salmon" /> : <CheckIcon size={14} />}
            {r}
          </span>
          <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${reqTone[t]}`}>{t}</span>
        </li>
      ))}
    </ul>
  </VisualFrame>
);

const V3 = () => (
  <VisualFrame tint="linear-gradient(160deg, var(--chart-salmon), var(--highlight) 60%, var(--chart-cyan))">
    <p className="text-[12px] font-medium text-ink">Tailored bullet</p>
    <p className="mt-3 text-[11px] text-muted line-through">Made weekly reports in Excel.</p>
    <p className="mt-1.5 text-[12px] leading-snug text-ink">Automated the weekly operations report in Excel, cutting prep from 6 hours to 1.</p>
    <p className="mt-3 inline-flex items-center gap-1 rounded-full bg-fit-strong px-2 py-1 text-[10px] font-medium text-fit-strong-ink">
      <LinkIcon size={11} /> From your achievement
    </p>
  </VisualFrame>
);

const STEPS = [
  { n: "01", title: "Upload your resume.", text: "We pull out your real achievements. You review and edit every one.", Visual: V1 },
  { n: "02", title: "See an honest fit.", text: "Every requirement checked against your evidence, with gaps named, not hidden.", Visual: V2 },
  { n: "03", title: "Tailor with proof.", text: "Rewrite bullets for this job using only what you've done. Accept what you like.", Visual: V3 },
];

// Job: understand. Lever: effort minimisation (three steps feel small) + IKEA effect
// (step 1 says you edit). Active card expands; auto-advances every 5s, pauses on
// hover/focus, and never auto-advances with reduced motion.
export function Steps() {
  const [active, setActive] = useState(0);
  const [paused, setPaused] = useState(false);
  const reduce = useReducedMotion();

  useEffect(() => {
    if (paused || reduce) return;
    const id = setInterval(() => setActive((a) => (a + 1) % STEPS.length), 5000);
    return () => clearInterval(id);
  }, [paused, reduce]);

  return (
    <section id="how" aria-labelledby="how-h" className="scroll-mt-28">
      <Container>
        <h2 id="how-h" className="sr-only">How it works</h2>
        <Appear>
          <div
            className="flex flex-col gap-2 rounded-panel bg-well p-2 lg:flex-row"
            onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}
            onFocus={() => setPaused(true)} onBlur={() => setPaused(false)}
          >
            {STEPS.map((s, i) => {
              const on = i === active;
              return (
                <motion.div
                  key={s.n}
                  animate={{ flexGrow: on ? 2.05 : 1 }}
                  transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 260, damping: 30 }}
                  className={`relative flex min-w-0 flex-col rounded-card p-6 lg:min-h-[340px] lg:basis-0 lg:overflow-hidden ${on ? "bg-card shadow-card" : "bg-card-soft"}`}
                >
                  <button
                    type="button" aria-pressed={on} onClick={() => setActive(i)}
                    className="flex min-w-0 flex-1 flex-col text-left focus-visible:outline-none after:absolute after:inset-0 after:rounded-card focus-visible:after:outline-2 focus-visible:after:outline-ink lg:w-[210px]"
                  >
                    <span className="text-lg text-faint">{s.n}</span>
                    <span className="mt-auto block pt-10 font-display text-[26px] leading-[1.3] tracking-[-0.04em] text-ink">{s.title}</span>
                    <span className="mt-3 block text-base leading-[1.4] text-muted">{s.text}</span>
                  </button>
                  <div className={`mt-5 w-full lg:absolute lg:inset-y-6 lg:right-6 lg:mt-0 lg:w-[230px] ${on ? "" : "lg:hidden"}`}>
                    <motion.div key={on ? "on" : "off"} data-appear=""
                      initial={on ? { opacity: 0, x: 16 } : false} animate={{ opacity: 1, x: 0 }}
                      transition={{ duration: 0.45, ease: EASE, delay: 0.1 }} className="h-full">
                      <s.Visual />
                    </motion.div>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </Appear>
      </Container>
    </section>
  );
}
