"use client";

import { useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Appear, EASE } from "./motion";
import { CheckIcon, ColumnsIcon, Container, GaugeIcon, H2, Lead, LinkIcon, PencilIcon, SampleTag, StackIcon, WandIcon } from "./shared";

function MockFrame({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative h-[300px] overflow-hidden rounded-[16px] bg-band sm:h-[390px]">
      <div aria-hidden="true" className="absolute inset-0 opacity-60" style={{ background: "radial-gradient(60% 70% at 30% 90%, var(--band-red), transparent 70%), radial-gradient(50% 60% at 90% 10%, var(--band-green), transparent 70%)", filter: "blur(30px)" }} />
      <div className="absolute bottom-[-24px] left-6 right-[-24px] top-8 rounded-[16px] bg-on-dark p-5 pr-10 sm:left-8 sm:top-10 sm:p-7 sm:pr-12">{children}</div>
    </div>
  );
}

const FitMock = () => (
  <MockFrame>
    <div className="flex items-center justify-between"><p className="text-lg font-medium text-ink">Data Analyst, Operations</p><SampleTag /></div>
    <p className="mt-1 inline-block rounded-full bg-fit-strong px-2 py-0.5 text-[12px] font-medium text-fit-strong-ink">Strong fit</p>
    <ul className="mt-3 space-y-2.5 text-[15px] text-ink">
      <li className="flex items-center gap-2"><CheckIcon size={14} />SQL: daily in your last two roles</li>
      <li className="flex items-center gap-2"><CheckIcon size={14} />Excel reporting: you rebuilt it</li>
      <li className="flex items-center gap-2"><CheckIcon size={14} />Process improvement: prep cut from 6h to 1h</li>
      <li className="flex items-center gap-2 rounded-[8px] bg-fit-plausible px-1.5 py-1 text-fit-plausible-ink"><CheckIcon size={14} />Adjacent: stakeholder updates</li>
      <li className="flex items-center gap-2 rounded-[8px] bg-fit-weak px-1.5 py-1 text-fit-weak-ink"><span aria-hidden="true" className="h-3.5 w-3.5 rounded-full border border-current" />Gap: Power BI not shown</li>
    </ul>
  </MockFrame>
);
const EvidenceMock = () => (
  <MockFrame>
    <p className="text-lg font-medium text-ink">Evidence bank</p>
    <ul className="mt-3 space-y-2">
      {[["Automated weekly ops report", "Excel · SQL"], ["Ran monthly ops review", "Stakeholders"], ["Cleaned 3 years of sales data", "Data quality"]].map(([t, k]) => (
        <li key={t} className="flex items-center justify-between gap-2 rounded-[10px] bg-quiet px-3 py-2">
          <span><span className="block text-[15px] text-ink">{t}</span><span className="block text-[12px] text-muted">{k}</span></span>
          <PencilIcon size={14} className="text-muted" />
        </li>
      ))}
    </ul>
  </MockFrame>
);
const TailorMock = () => (
  <MockFrame>
    <p className="text-lg font-medium text-ink">Suggested rewrite</p>
    <p className="mt-3 text-[14px] text-muted line-through">Responsible for reports.</p>
    <p className="mt-1 text-[15px] leading-snug text-ink">Automated the weekly operations report, cutting prep from 6 hours to 1.</p>
    <p className="mt-3 inline-flex items-center gap-1 rounded-full bg-fit-strong px-2 py-1 text-[12px] text-fit-strong-ink"><LinkIcon size={12} />Cites: weekly ops report</p>
    <p className="mt-2 text-[12px] text-muted">1 suggestion dropped: no evidence</p>
  </MockFrame>
);
const TrackerMock = () => (
  <MockFrame>
    <p className="text-lg font-medium text-ink">Applied</p>
    <div className="mt-3 rounded-[10px] border border-line p-3">
      <p className="text-[15px] text-ink">Reporting Analyst · Cedar Credit Union</p>
      <p className="mt-2 rounded-[8px] bg-highlight px-2 py-1.5 text-[14px] text-ink">Applied 8 days ago. Follow up?</p>
    </div>
    <p className="mt-2 text-[12px] text-muted">Reminders can be turned off anytime.</p>
  </MockFrame>
);

const TABS = [
  { id: "fit", label: "Fit check", Icon: GaugeIcon, badge: "Fit check", title: "A reason for every score.", body: "Each requirement in the posting is checked against your own achievements: met, adjacent, or a gap.", diff: "Others give a number; we show which requirements you meet.", Mock: FitMock },
  { id: "evidence", label: "Evidence bank", Icon: StackIcon, badge: "Evidence bank", title: "Your experience, structured and yours to edit.", body: "We turn your resume into achievements you can check, fix and add to. Everything else draws on them.", diff: "Nothing is matched until you've reviewed it.", Mock: EvidenceMock },
  { id: "tailor", label: "Tailoring", Icon: WandIcon, badge: "Tailoring", title: "Bullets you can defend in an interview.", body: "Rewrites for a specific job, each one citing the achievement it came from. You accept or reject every line.", diff: "Anything without evidence is dropped.", Mock: TailorMock },
  { id: "tracker", label: "Tracker", Icon: ColumnsIcon, badge: "Tracker", title: "Know what's next.", body: "Saved, tailored, applied, interview: one board, updated by you, with a quiet nudge when it's time.", diff: "Follow-up reminders after 7 days.", Mock: TrackerMock },
];

// Job: understand. Lever: show-don't-tell, depth on demand (one tab at a time).
export function FeatureTabs() {
  const [i, setI] = useState(0);
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const t = TABS[i];

  function onKey(e: React.KeyboardEvent) {
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    const n = (i + d + TABS.length) % TABS.length;
    setI(n);
    refs.current[n]?.focus();
  }

  return (
    <section id="features" aria-labelledby="features-h" className="py-28 sm:py-40">
      <Container>
        <Appear className="mx-auto max-w-[620px] text-center">
          <H2 id="features-h">Built to be honest</H2>
          <Lead className="mt-4">Every part of Fitwise shows its working, so you can trust the result and say it out loud in an interview.</Lead>
        </Appear>
        <Appear delay={0.1} className="mt-14">
          <div role="tablist" aria-label="Features" onKeyDown={onKey}
            className="grid grid-cols-2 gap-1 rounded-[40px] bg-quiet p-2 sm:grid-cols-4">
            {TABS.map((x, n) => (
              <button key={x.id} ref={(el) => { refs.current[n] = el; }} role="tab" id={`tab-${x.id}`} aria-selected={n === i}
                aria-controls={`panel-${x.id}`} tabIndex={n === i ? 0 : -1} onClick={() => setI(n)}
                className={`relative flex min-h-11 items-center justify-center gap-2 rounded-pill px-3 py-3 text-[15px] font-medium transition-colors sm:text-base ${n === i ? "text-ink" : "text-faint hover:text-muted"}`}>
                {n === i && <motion.span layoutId="tab-pill" data-appear="" className="absolute inset-0 rounded-pill bg-on-dark" transition={{ type: "spring", stiffness: 380, damping: 34 }} />}
                <x.Icon size={17} className="relative" />
                <span className="relative">{x.label}</span>
              </button>
            ))}
          </div>
          <div className="mt-3 rounded-card bg-glass p-2">
            <AnimatePresence mode="wait" initial={false}>
              <motion.div key={t.id} role="tabpanel" id={`panel-${t.id}`} aria-labelledby={`tab-${t.id}`} data-appear=""
                initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.35, ease: EASE }}
                className="grid items-center gap-6 md:grid-cols-[1fr_1fr] md:gap-10">
                <t.Mock />
                <div className="px-3 pb-6 md:px-2 md:py-8">
                  <span className="inline-block rounded-full bg-highlight px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.02em] text-ink">{t.badge}</span>
                  <h3 className="mt-5 font-display text-[28px] leading-[1.25] tracking-[-0.04em] text-ink sm:text-[36px]">{t.title}</h3>
                  <p className="mt-4 text-base leading-[1.45] text-muted">{t.body}</p>
                  <p className="mt-4 flex items-start gap-2 text-base text-ink"><CheckIcon size={18} className="mt-0.5 shrink-0" />{t.diff}</p>
                </div>
              </motion.div>
            </AnimatePresence>
          </div>
        </Appear>
      </Container>
    </section>
  );
}
