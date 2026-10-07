"use client";

import { useId, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Appear, EASE } from "./motion";
import { Container, H2, Lead, Pill } from "./shared";
import { FAQS } from "./faqs";

// Job: compel. Lever: objection handling right before the ask (cost, honesty,
// control, data, fit for my field, exit), one open at a time.
export function Faq() {
  const [open, setOpen] = useState<number | null>(null);
  const base = useId();

  return (
    <section id="faq" aria-labelledby="faq-h" className="scroll-mt-24 py-28 sm:py-40">
      <Container className="grid gap-10 md:grid-cols-[1fr_600px] md:gap-12">
        <Appear>
          <H2 id="faq-h">Your questions, answered honestly</H2>
          <Lead className="mt-4 max-w-[340px]">What people ask before they trust a tool with their resume.</Lead>
          <div className="mt-6"><Pill tone="ghost">Start free</Pill></div>
        </Appear>
        <Appear delay={0.1}>
          <ul className="space-y-2 rounded-panel bg-well p-2">
            {FAQS.map((f, i) => {
              const on = open === i;
              const bid = `${base}-b${i}`, pid = `${base}-p${i}`;
              return (
                <li key={f.q} className="rounded-card bg-glass">
                  <h3>
                    <button id={bid} type="button" aria-expanded={on} aria-controls={pid} onClick={() => setOpen(on ? null : i)}
                      className="flex w-full items-center justify-between gap-4 rounded-card px-6 py-6 text-left font-display text-[20px] leading-[1.3] tracking-[-0.04em] text-ink sm:px-8">
                      {f.q}
                      <motion.span aria-hidden="true" animate={{ rotate: on ? 45 : 0 }} transition={{ duration: 0.3, ease: EASE }}
                        className="shrink-0 text-faint">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"><path d="M12 4v16M4 12h16" /></svg>
                      </motion.span>
                    </button>
                  </h3>
                  <AnimatePresence initial={false}>
                    {on && (
                      <motion.div id={pid} role="region" aria-labelledby={bid}
                        initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.3, ease: EASE }} className="overflow-hidden">
                        <p className="px-6 pb-7 text-base leading-[1.5] text-muted sm:px-8">{f.a}</p>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </li>
              );
            })}
          </ul>
        </Appear>
      </Container>
    </section>
  );
}
