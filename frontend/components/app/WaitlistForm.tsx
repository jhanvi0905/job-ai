"use client";

import { useState } from "react";
import { api } from "@/lib/product-api";
import { Button, inputClass } from "./ui";

export function WaitlistForm({ source = "landing" }: { source?: string }) {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setState("busy");
    try { await api.joinWaitlist(email, source); setState("done"); }
    catch { setState("error"); }
  }

  if (state === "done") {
    return <p role="status" className="rounded-lg bg-emerald-50 p-3 text-sm font-medium text-emerald-800">You&apos;re on the list. We&apos;ll email you once when your spot opens.</p>;
  }
  return (
    <form onSubmit={submit} className="w-full max-w-md" aria-label="Join the waitlist">
      <div className="flex flex-col gap-2 sm:flex-row">
        <label className="sr-only" htmlFor={`wl-${source}`}>Email address</label>
        <input id={`wl-${source}`} className={inputClass} type="email" required autoComplete="email" placeholder="you@example.com" value={email} onChange={(e) => setEmail(e.target.value)} />
        <Button type="submit" disabled={state === "busy"} className="shrink-0">{state === "busy" ? "Joining…" : "Join the waitlist"}</Button>
      </div>
      {state === "error" && <p role="alert" className="mt-2 text-sm text-red-700">That didn&apos;t go through. Please try again in a moment.</p>}
      <p className="mt-2 text-xs text-slate-500">One email when access opens. No spam, no sharing.</p>
    </form>
  );
}
