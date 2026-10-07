"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LogoMark } from "@/components/marketing/Nav";
import { SIGNUP_EMAIL_KEY } from "@/components/marketing/FinalCta";
import { api } from "@/lib/product-api";
import { getSupabase } from "@/lib/supabase/client";
import { isSupabaseConfigured, safeNextPath } from "@/lib/supabase/config";
import { Button, Card, ErrorNotice, Field, inputClass, Spinner } from "./ui";

type Router = ReturnType<typeof useRouter>;

// ---- shared helpers -------------------------------------------------------------------

function nextFromUrl(): string {
  if (typeof window === "undefined") return "";
  return safeNextPath(new URLSearchParams(window.location.search).get("next"));
}

/** Where Supabase sends the browser back to after an email link or OAuth round trip. */
function callbackUrl(next?: string): string {
  const url = new URL("/auth/callback", window.location.origin);
  const safe = safeNextPath(next);
  if (safe) url.searchParams.set("next", safe);
  return url.toString();
}

/**
 * After any successful sign-in: provision/fetch the product user once (GET /me), then go
 * to the page the user was headed to, or onboarding if they have no achievements yet.
 */
export async function routeAfterSignIn(router: Router, next = "") {
  await api.me();
  const dest = safeNextPath(next);
  if (dest) {
    router.replace(dest);
    return;
  }
  let hasAchievements = true;
  try { hasAchievements = (await api.getAchievements()).length > 0; } catch { /* default to the feed */ }
  router.replace(hasAchievements ? "/feed" : "/onboarding");
}

function AuthHeader() {
  return (
    <Link href="/" className="mb-8 inline-flex items-center justify-center gap-2 text-ink">
      <LogoMark /><span className="font-display text-[24px] tracking-[-0.04em]">Fitwise</span>
    </Link>
  );
}

function Title({ children }: { children: React.ReactNode }) {
  return <h1 className="font-display text-[32px] leading-[1.15] tracking-[-0.05em] text-ink">{children}</h1>;
}

/** Shown instead of the form when NEXT_PUBLIC_SUPABASE_* are missing. */
function NotConfigured() {
  const dev = process.env.NODE_ENV !== "production";
  return (
    <div role="alert" className="mt-4 rounded-card bg-highlight p-5 text-[15px] leading-[1.45] text-ink">
      {dev ? (
        <>
          <p className="font-medium">Supabase isn&apos;t configured (dev notice).</p>
          <p className="mt-1">
            Set <code className="font-mono text-sm">NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
            <code className="font-mono text-sm">NEXT_PUBLIC_SUPABASE_ANON_KEY</code> in{" "}
            <code className="font-mono text-sm">frontend/.env.local</code>, then restart the dev server.
          </p>
        </>
      ) : (
        <p className="font-medium">Sign-in is temporarily unavailable. Please try again later.</p>
      )}
    </div>
  );
}

function CheckEmail({ email, what, onBack }: { email: string; what: string; onBack: () => void }) {
  return (
    <div role="status" className="mt-4 space-y-3">
      <div className="rounded-card bg-glass p-5 text-[15px] leading-[1.45] text-ink">
        <p className="font-medium">Check your email</p>
        <p className="mt-1 text-muted">
          We sent {what} to <span className="font-medium text-ink">{email}</span>. Open it on this device to continue.
        </p>
      </div>
      <Button variant="ghost" className="w-full" onClick={onBack}>Use a different email</Button>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18">
      <path fill="#4285F4" d="M23.5 12.3c0-.8-.1-1.6-.2-2.3H12v4.4h6.5a5.6 5.6 0 0 1-2.4 3.7v3h3.9c2.3-2.1 3.5-5.2 3.5-8.8z" />
      <path fill="#34A853" d="M12 24c3.2 0 6-1.1 8-2.9l-3.9-3a7.2 7.2 0 0 1-10.8-3.8h-4v3.1A12 12 0 0 0 12 24z" />
      <path fill="#FBBC05" d="M5.3 14.3a7.2 7.2 0 0 1 0-4.6V6.6h-4a12 12 0 0 0 0 10.8l4-3.1z" />
      <path fill="#EA4335" d="M12 4.8c1.8 0 3.4.6 4.6 1.8l3.4-3.4A12 12 0 0 0 1.3 6.6l4 3.1A7.2 7.2 0 0 1 12 4.8z" />
    </svg>
  );
}

// ---- sign in / sign up ----------------------------------------------------------------

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState<null | "password" | "magic" | "google">(null);
  const [error, setError] = useState<unknown>(null);
  const [sent, setSent] = useState<null | "confirm" | "magic">(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const isSignup = mode === "signup";

  // Prefill from the landing page's final CTA (sessionStorage, never the URL). Read once.
  useEffect(() => {
    if (!isSignup) return;
    let v: string | null = null;
    try { v = window.sessionStorage.getItem(SIGNUP_EMAIL_KEY); window.sessionStorage.removeItem(SIGNUP_EMAIL_KEY); } catch { /* storage unavailable */ }
    if (!v) return;
    const id = setTimeout(() => setEmail((cur) => cur || v), 0);
    return () => clearTimeout(id);
  }, [isSignup]);

  // Errors handed back by /auth/callback (expired or reused link).
  useEffect(() => {
    const msg = new URLSearchParams(window.location.search).get("error");
    if (!msg) return;
    const id = setTimeout(() => setError(new Error(msg)), 0);
    return () => clearTimeout(id);
  }, []);

  if (!isSupabaseConfigured) {
    return (
      <>
        <AuthHeader />
        <Card><Title>{isSignup ? "Create your account" : "Welcome back"}</Title><NotConfigured /></Card>
      </>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const supabase = getSupabase();
    if (!supabase) return;
    setBusy("password");
    setError(null);
    try {
      if (isSignup) {
        const { data, error: err } = await supabase.auth.signUp({
          email, password, options: { emailRedirectTo: callbackUrl(nextFromUrl()) },
        });
        if (err) throw err;
        // Email confirmation on: no session until the link is clicked.
        if (!data.session) { setSent("confirm"); setBusy(null); return; }
      } else {
        const { error: err } = await supabase.auth.signInWithPassword({ email, password });
        if (err) throw err;
      }
      await routeAfterSignIn(router, nextFromUrl());
    } catch (err) {
      setError(err);
      setBusy(null);
    }
  }

  async function magicLink() {
    const supabase = getSupabase();
    if (!supabase) return;
    if (!email || !emailRef.current?.checkValidity()) {
      emailRef.current?.reportValidity();
      return;
    }
    setBusy("magic");
    setError(null);
    try {
      const { error: err } = await supabase.auth.signInWithOtp({
        email, options: { emailRedirectTo: callbackUrl(nextFromUrl()) },
      });
      if (err) throw err;
      setSent("magic");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  }

  async function google() {
    const supabase = getSupabase();
    if (!supabase) return;
    setBusy("google");
    setError(null);
    const { error: err } = await supabase.auth.signInWithOAuth({
      provider: "google", options: { redirectTo: callbackUrl(nextFromUrl()) },
    });
    // On success the browser is already navigating to Google.
    if (err) { setError(err); setBusy(null); }
  }

  return (
    <>
      <AuthHeader />
      <Card>
        <Title>{isSignup ? "Create your account" : "Welcome back"}</Title>
        {sent ? (
          <CheckEmail
            email={email}
            what={sent === "confirm" ? "a confirmation link" : "a sign-in link"}
            onBack={() => { setSent(null); setPassword(""); }}
          />
        ) : (
          <>
            <Button variant="secondary" className="mt-4 w-full" onClick={google} disabled={busy !== null}>
              <GoogleIcon />{busy === "google" ? "Redirecting…" : "Continue with Google"}
            </Button>
            <div className="my-4 flex items-center gap-3 text-xs text-faint" aria-hidden="true">
              <span className="h-px flex-1 bg-line" />or<span className="h-px flex-1 bg-line" />
            </div>
            <form onSubmit={submit} className="space-y-4">
              <Field label="Email">
                <input ref={emailRef} className={inputClass} type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </Field>
              <Field label="Password" hint={isSignup ? "At least 8 characters." : undefined}>
                <input className={inputClass} type="password" required minLength={isSignup ? 8 : undefined}
                  autoComplete={isSignup ? "new-password" : "current-password"} value={password} onChange={(e) => setPassword(e.target.value)} />
              </Field>
              {!isSignup && (
                <p className="-mt-2 text-right text-sm">
                  <Link href="/forgot-password" className="text-muted underline underline-offset-4 hover:text-ink">Forgot password?</Link>
                </p>
              )}
              {error != null && <ErrorNotice error={error} />}
              <Button type="submit" className="w-full" disabled={busy !== null}>
                {busy === "password" ? "Please wait…" : isSignup ? "Sign up" : "Log in"}
              </Button>
              <Button variant="ghost" className="w-full" onClick={magicLink} disabled={busy !== null}>
                {busy === "magic" ? "Sending…" : "Email me a magic link"}
              </Button>
            </form>
          </>
        )}
      </Card>
      {isSignup && !sent && (
        <p className="mt-4 text-center text-sm text-muted">
          By continuing you agree to the{" "}
          <Link href="/terms" className="font-medium text-ink underline underline-offset-4">Terms</Link> and{" "}
          <Link href="/privacy" className="font-medium text-ink underline underline-offset-4">Privacy Policy</Link>.
        </p>
      )}
      <p className="mt-4 text-center text-sm text-slate-600">
        {isSignup ? "Already have an account? " : "New here? "}
        <Link href={isSignup ? "/login" : "/signup"} className="font-medium text-ink underline underline-offset-4">
          {isSignup ? "Log in" : "Create an account"}
        </Link>
      </p>
    </>
  );
}

// ---- forgot / reset password ----------------------------------------------------------

export function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const supabase = getSupabase();
    if (!supabase) return;
    setBusy(true);
    setError(null);
    try {
      const { error: err } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: callbackUrl("/reset-password"),
      });
      if (err) throw err;
      setSent(true);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <AuthHeader />
      <Card>
        <Title>Reset your password</Title>
        {!isSupabaseConfigured ? <NotConfigured /> : sent ? (
          <CheckEmail email={email} what="a password reset link" onBack={() => setSent(false)} />
        ) : (
          <form onSubmit={submit} className="mt-4 space-y-4">
            <p className="text-[15px] leading-[1.45] text-muted">Enter your account email and we&apos;ll send you a link to choose a new password.</p>
            <Field label="Email">
              <input className={inputClass} type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
            </Field>
            {error != null && <ErrorNotice error={error} />}
            <Button type="submit" className="w-full" disabled={busy}>{busy ? "Sending…" : "Send reset link"}</Button>
          </form>
        )}
      </Card>
      <p className="mt-4 text-center text-sm text-slate-600">
        Remembered it? <Link href="/login" className="font-medium text-ink underline underline-offset-4">Log in</Link>
      </p>
    </>
  );
}

export function ResetPasswordForm() {
  const router = useRouter();
  const [state, setState] = useState<"checking" | "ready" | "no-session">("checking");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  // The recovery link lands here via /auth/callback, which set a session cookie.
  useEffect(() => {
    let cancelled = false;
    const supabase = getSupabase();
    if (!supabase) return;
    supabase.auth.getSession().then(({ data }) => {
      if (!cancelled) setState(data.session ? "ready" : "no-session");
    });
    return () => { cancelled = true; };
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const supabase = getSupabase();
    if (!supabase) return;
    if (password !== confirm) { setError(new Error("Passwords don't match.")); return; }
    setBusy(true);
    setError(null);
    try {
      const { error: err } = await supabase.auth.updateUser({ password });
      if (err) throw err;
      await routeAfterSignIn(router);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  let body: React.ReactNode;
  if (!isSupabaseConfigured) body = <NotConfigured />;
  else if (state === "checking") body = <div className="mt-4"><Spinner /></div>;
  else if (state === "no-session") {
    body = (
      <div role="alert" className="mt-4 space-y-3 text-[15px] leading-[1.45] text-muted">
        <p>This reset link is invalid or has expired.</p>
        <Link href="/forgot-password" className="font-medium text-ink underline underline-offset-4">Send a new link</Link>
      </div>
    );
  } else {
    body = (
      <form onSubmit={submit} className="mt-4 space-y-4">
        <Field label="New password" hint="At least 8 characters.">
          <input className={inputClass} type="password" required minLength={8} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Field label="Confirm new password">
          <input className={inputClass} type="password" required minLength={8} autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </Field>
        {error != null && <ErrorNotice error={error} />}
        <Button type="submit" className="w-full" disabled={busy}>{busy ? "Saving…" : "Set new password"}</Button>
      </form>
    );
  }

  return (
    <>
      <AuthHeader />
      <Card><Title>Choose a new password</Title>{body}</Card>
    </>
  );
}

// ---- post-callback hand-off -----------------------------------------------------------

/** /auth/continue: the callback set the session cookie; provision the user and route. */
export function AuthContinue() {
  const router = useRouter();
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    routeAfterSignIn(router, nextFromUrl()).catch(setError);
  }, [router]);

  return (
    <>
      <AuthHeader />
      <Card>
        <Title>Signing you in</Title>
        <div className="mt-4">
          {error != null ? (
            <div className="space-y-3">
              <ErrorNotice error={error} />
              <Link href="/login" className="text-sm font-medium text-ink underline underline-offset-4">Back to log in</Link>
            </div>
          ) : <Spinner />}
        </div>
      </Card>
    </>
  );
}
