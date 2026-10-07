"use client";

import { motion, type Variants } from "motion/react";

/*
 * Framer-style "appear" (spec §1 Motion): opacity 0→1, y 24→0, blur 6px→0, 0.7s,
 * ease [0.22,1,0.36,1], once, at ~15% in view, stagger 0.08s within a group.
 * Reduced motion: globals.css forces [data-appear] to its final state (no transform,
 * no blur) with !important, so server and client markup stay identical (no
 * hydration mismatch from reading the media query during render).
 */
export const EASE = [0.22, 1, 0.36, 1] as const;

const hidden = { opacity: 0, y: 24, filter: "blur(6px)" };
const shown = { opacity: 1, y: 0, filter: "blur(0px)" };
const item: Variants = { hidden, shown: { ...shown, transition: { duration: 0.7, ease: EASE } } };

type Tag = "div" | "section" | "ul" | "ol" | "li" | "p" | "span";

export function Appear({
  children, className = "", delay = 0, as = "div", y = 24,
}: { children: React.ReactNode; className?: string; delay?: number; as?: Tag; y?: number }) {
  const C = motion[as];
  return (
    <C
      data-appear=""
      className={className}
      initial={{ ...hidden, y }}
      whileInView={shown}
      transition={{ duration: 0.7, ease: EASE, delay }}
      viewport={{ once: true, amount: 0.15 }}
    >
      {children}
    </C>
  );
}

/** Parent that staggers its <AppearItem> children by 0.08s. */
export function AppearGroup({
  children, className = "", as = "div",
}: { children: React.ReactNode; className?: string; as?: Tag }) {
  const C = motion[as];
  return (
    <C className={className} initial="hidden" whileInView="shown" viewport={{ once: true, amount: 0.15 }}
      variants={{ hidden: {}, shown: { transition: { staggerChildren: 0.08 } } }}>
      {children}
    </C>
  );
}

export function AppearItem({
  children, className = "", as = "div",
}: { children: React.ReactNode; className?: string; as?: Tag }) {
  const C = motion[as];
  return <C data-appear="" className={className} variants={item}>{children}</C>;
}
