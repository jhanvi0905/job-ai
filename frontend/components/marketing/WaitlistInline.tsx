"use client";

import { useId, useState } from "react";
import { api } from "@/lib/product-api";
import { ArrowChip, pillClass, type PillTone } from "./shared";

/** Grovia-style pill email field with the button inside it. One email when access opens. */
export function WaitlistInline({
  source, tone = "black", onDark = false, label = "Join the waitlist",
}: { source: string; tone?: PillTone; onDark?: boolean; label?: string }) {
  const id = useId();
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setState("busy");
    try { await api.joinWaitlist(email, source); setState("done"); }
    catch { setState("error"); }
  }

  const text = onDark ? "text-on-dark" : "text-ink";
  if (state === "done") {
    return <p role="status" className={`text-base ${text}`}>You&apos;re on the list. We&apos;ll email you once, when your spot opens.</p>;
  }
  return (
    <form onSubmit={submit} aria-label="Join the waitlist" className="w-full max-w-[520px]">
      <div className={`flex flex-col gap-2 rounded-[28px] p-1 sm:flex-row sm:items-center ${onDark ? "bg-on-dark-fill" : "bg-canvas"}`}>
        <label htmlFor={id} className="sr-only">Email address</label>
        <input
          id={id} type="email" required autoComplete="email" placeholder="you@example.com" value={email}
          onChange={(e) => setEmail(e.target.value)}
          className={`h-11 min-w-0 flex-1 rounded-full bg-transparent px-4 text-base outline-none placeholder:text-faint focus-visible:outline-2 focus-visible:outline-offset-2 ${onDark ? "text-on-dark focus-visible:outline-on-dark" : "text-ink focus-visible:outline-ink"}`}
        />
        <button type="submit" disabled={state === "busy"} className={pillClass(tone, "justify-center")}>
          {state === "busy" ? "Joining…" : label}
          <ArrowChip tone={tone} />
        </button>
      </div>
      {state === "error" && <p role="alert" className={`mt-2 text-sm ${text}`}>That didn&apos;t go through. Please try again in a moment.</p>}
    </form>
  );
}
