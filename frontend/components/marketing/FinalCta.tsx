"use client";

import { useId, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/product-api";
import { Appear } from "./motion";
import { ArrowChip, Container, CTA_LABEL, H2, pillClass, TrustLines } from "./shared";

/** Hand-off key read by the signup form to prefill the email (never put in the URL). */
export const SIGNUP_EMAIL_KEY = "fitwise.signupEmail";

// Job: compel. Lever: final low-friction ask; one field, one button, trust lines beside it.
export function FinalCta() {
  const id = useId();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [wl, setWl] = useState<"idle" | "busy" | "done" | "error">("idle");

  function start(e: React.FormEvent) {
    e.preventDefault();
    try { window.sessionStorage.setItem(SIGNUP_EMAIL_KEY, email); } catch { /* storage unavailable: user retypes */ }
    router.push("/signup");
  }
  async function waitlist() {
    if (!email || !/\S+@\S+\.\S+/.test(email)) { setWl("error"); return; }
    setWl("busy");
    try { await api.joinWaitlist(email, "final-cta"); setWl("done"); } catch { setWl("error"); }
  }

  return (
    <section aria-labelledby="final-h" className="px-2 sm:px-4">
      <div className="band-dark rounded-band py-20 sm:py-24">
        <Container className="grid gap-12 lg:grid-cols-[1fr_560px] lg:gap-10">
          <Appear className="flex flex-col">
            <H2 id="final-h" onDark>Find the jobs worth your time.</H2>
            <p className="mt-4 max-w-[380px] text-lg leading-[1.4] text-on-dark-muted">Upload your resume and see your first honest fit in minutes.</p>
            <TrustLines onDark className="mt-10 lg:mt-auto" />
          </Appear>
          <Appear delay={0.12}>
            <form onSubmit={start} className="glass-dark rounded-panel p-7 sm:p-8">
              <label htmlFor={id} className="block text-base text-on-dark">Email</label>
              <input id={id} type="email" required autoComplete="email" placeholder="you@example.com" value={email}
                onChange={(e) => { setEmail(e.target.value); if (wl === "error") setWl("idle"); }}
                className="mt-3 h-12 w-full rounded-[14px] bg-on-dark-fill px-4 text-base text-on-dark outline-none placeholder:text-on-dark-muted focus-visible:outline-2 focus-visible:outline-on-dark" />
              <p className="mt-3 text-sm text-on-dark-muted">You&apos;ll set a password next. No card.</p>
              <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-3">
                <button type="submit" className={pillClass("yellow")}>{CTA_LABEL}<ArrowChip tone="yellow" /></button>
                <button type="button" onClick={waitlist} disabled={wl === "busy"}
                  className="inline-flex min-h-11 items-center text-base text-on-dark underline underline-offset-4 hover:text-on-dark-muted">
                  {wl === "busy" ? "Joining…" : "or join the waitlist"}
                </button>
              </div>
              <p role="status" className="mt-3 min-h-5 text-sm text-on-dark">
                {wl === "done" && "You're on the waitlist. One email when your spot opens."}
                {wl === "error" && "Enter a valid email above, then try again."}
              </p>
            </form>
          </Appear>
        </Container>
      </div>
    </section>
  );
}
