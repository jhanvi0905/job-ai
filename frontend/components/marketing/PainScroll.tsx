"use client";

import { useRef } from "react";
import { motion, useScroll, useTransform, type MotionValue } from "motion/react";
import { Container } from "./shared";

const STATEMENT =
  "You've sent dozens of applications. Most never got a reply. Not because you're not good, but because nobody told you which jobs were worth it, or how to show what you've actually done.";
const WORDS = STATEMENT.split(" ");

function Word({ progress, i, n, children }: { progress: MotionValue<number>; i: number; n: number; children: string }) {
  const start = i / n;
  const color = useTransform(progress, [start, Math.min(1, start + 2 / n)], ["var(--faint)", "var(--ink)"]);
  return <motion.span data-pain-word="" style={{ color }}>{children} </motion.span>;
}

// Job: highlight. Lever: resonance before any product is shown; the words darken in
// step with the reader's scroll. Reduced motion: globals.css renders them all in ink.
export function PainScroll() {
  const ref = useRef<HTMLParagraphElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 0.85", "end 0.5"] });

  return (
    <section aria-labelledby="pain-h" className="py-24 sm:py-36">
      <Container>
        <h2 id="pain-h" className="sr-only">Sound familiar?</h2>
        <p ref={ref} className="mx-auto max-w-[820px] text-center font-display text-[28px] leading-[1.2] tracking-[-0.05em] sm:text-[40px] sm:leading-[1.15]">
          {WORDS.map((w, i) => <Word key={i} progress={scrollYProgress} i={i} n={WORDS.length}>{w}</Word>)}
        </p>
      </Container>
    </section>
  );
}
