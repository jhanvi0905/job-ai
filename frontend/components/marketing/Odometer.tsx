"use client";

import { useEffect, useLayoutEffect } from "react";
import { useAnimate, useInView, useReducedMotion } from "motion/react";
import { EASE } from "./motion";

const useIsoLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

/**
 * Odometer: each digit is a 0-9 wheel. The server renders the final value (right for
 * no-JS, LCP and reduced motion); on the client the wheels reset to 0 before paint
 * and roll into place once the number is in view. Screen readers get the value once.
 */
export function Odometer({ value, className = "" }: { value: number; className?: string }) {
  const digits = String(Math.max(0, Math.round(value))).split("").map(Number);
  const [scope, animate] = useAnimate<HTMLSpanElement>();
  const inView = useInView(scope, { once: true, amount: 0.6 });
  const reduce = useReducedMotion();

  useIsoLayoutEffect(() => {
    if (reduce || !scope.current) return;
    scope.current.querySelectorAll<HTMLElement>("[data-wheel]").forEach((el) => { el.style.transform = "translateY(0%)"; });
  }, [reduce, scope]);

  useEffect(() => {
    if (!inView || reduce || !scope.current) return;
    scope.current.querySelectorAll<HTMLElement>("[data-wheel]").forEach((el, i) => {
      const d = Number(el.dataset.wheel);
      animate(el, { transform: ["translateY(0%)", `translateY(-${d * 10}%)`] }, { duration: 1.1, delay: 0.35 + i * 0.09, ease: EASE });
    });
  }, [inView, reduce, animate, scope]);

  return (
    <span ref={scope} className={`inline-flex tabular-nums ${className}`}>
      <span className="sr-only">{value}</span>
      {digits.map((d, i) => (
        <span key={i} aria-hidden="true" className="relative inline-block h-[1em] overflow-hidden leading-none">
          <span data-wheel={d} className="flex flex-col" style={{ transform: `translateY(-${d * 10}%)` }}>
            {Array.from({ length: 10 }, (_, n) => <span key={n} className="block h-[1em] leading-none">{n}</span>)}
          </span>
        </span>
      ))}
    </span>
  );
}
