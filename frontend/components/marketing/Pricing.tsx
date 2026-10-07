"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Appear, EASE } from "./motion";
import { ArrowCircle, CheckIcon, Container, H2, Pill, SparkIcon, StackIcon, TrustLines } from "./shared";
import { WaitlistInline } from "./WaitlistInline";

const PLANS = [
  {
    id: "free", name: "Free", sub: "Everything you need to start", Icon: SparkIcon,
    price: "$0", per: "forever",
    desc: "Enough to feel the product work on your own resume and real jobs.",
    items: ["Limited daily job screening", "One resume parse", "One tailored resume", "Application tracker", "Delete your data anytime"],
  },
  {
    id: "pro", name: "Pro", sub: "Announced soon", Icon: StackIcon,
    price: "Price announced soon", per: "",
    desc: "For an active search. We'll set the price with waitlist members before launch.",
    items: ["Daily refresh of matches", "More tailored resumes", "More countries", "Everything in Free"],
  },
] as const;

// Job: compel. Lever: anchoring (Free shown beside Pro) and risk removal (trust lines
// instead of a rating; no invented price).
export function Pricing() {
  const [sel, setSel] = useState(0);
  const p = PLANS[sel];

  return (
    <section id="pricing" aria-labelledby="pricing-h" className="scroll-mt-24 px-2 sm:px-4">
      <div className="band-dark rounded-band py-20 sm:py-24">
        <Container className="grid gap-12 lg:grid-cols-[1fr_410px] lg:gap-10">
          <Appear>
            <H2 id="pricing-h" onDark>Simple pricing</H2>
            <div role="group" aria-label="Plans" className="mt-8 max-w-[356px] space-y-2 rounded-panel bg-on-dark-well p-2">
              {PLANS.map((x, n) => (
                <button key={x.id} type="button" aria-pressed={n === sel} onClick={() => setSel(n)}
                  className={`flex w-full items-center justify-between gap-3 rounded-[16px] px-5 py-4 text-left transition-colors bg-on-dark-fill ${n === sel ? "shadow-float" : "opacity-80 hover:opacity-100"}`}>
                  <span>
                    <span className={`block text-lg ${n === sel ? "text-on-dark" : "text-on-dark-muted"}`}>{x.name}</span>
                    <span className="block text-[13px] text-on-dark-muted">{x.sub}</span>
                  </span>
                  {n === sel && <ArrowCircle size={20} className="text-on-dark" />}
                </button>
              ))}
            </div>
            <TrustLines onDark className="mt-14" />
          </Appear>
          <Appear delay={0.12}>
            <div className="glass-dark rounded-panel p-7 sm:p-8">
              <AnimatePresence mode="wait" initial={false}>
                <motion.div key={p.id} data-appear="" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.3, ease: EASE }}>
                  <p className="flex items-center gap-3">
                    <span aria-hidden="true" className="flex h-10 w-10 items-center justify-center rounded-full bg-on-dark-fill"><p.Icon size={18} /></span>
                    <span className="font-display text-[28px] tracking-[-0.04em]">{p.name}</span>
                  </p>
                  <p className="mt-5 flex items-baseline gap-2">
                    <span className={`font-display tracking-[-0.05em] ${p.id === "free" ? "text-[40px]" : "text-[28px]"}`}>{p.price}</span>
                    {p.per && <span className="text-base text-on-dark-muted">/ {p.per}</span>}
                  </p>
                  <p className="mt-3 text-base leading-[1.45] text-on-dark-muted">{p.desc}</p>
                  <div className="mt-6">
                    {p.id === "free"
                      ? <Pill tone="yellow">Start free</Pill>
                      : <WaitlistInline source="pricing-pro" tone="yellow" onDark />}
                  </div>
                  <ul className="mt-7 space-y-3 text-base">
                    {p.items.map((it) => (
                      <li key={it} className="flex items-center gap-3"><CheckIcon size={16} />{it}</li>
                    ))}
                  </ul>
                </motion.div>
              </AnimatePresence>
            </div>
          </Appear>
        </Container>
      </div>
    </section>
  );
}
