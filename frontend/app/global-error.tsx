"use client";

// Last-resort boundary: replaces the root layout when it (or anything above a segment
// error.tsx) throws. Must render its own <html>/<body> and styles.
import { useEffect } from "react";
import * as Sentry from "@sentry/nextjs";
import "./globals.css";

export default function GlobalError({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en">
      <body className="min-h-screen bg-canvas font-sans text-ink antialiased">
        <title>Something went wrong | Fitwise</title>
        <main className="mx-auto flex min-h-screen max-w-[560px] flex-col items-center justify-center px-4 py-16 text-center">
          <span aria-hidden="true" className="flex h-12 w-12 items-center justify-center rounded-full bg-highlight text-2xl">!</span>
          <h1 className="mt-6 font-display text-[40px] leading-[1.1] tracking-[-0.05em]">Something went wrong</h1>
          <p className="mt-4 text-lg leading-[1.45] text-muted">
            Fitwise hit an unexpected error. Your data is safe. Try again, or head back to the start.
          </p>
          {error.digest && <p className="mt-3 font-mono text-xs text-faint">Reference: {error.digest}</p>}
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <button type="button" onClick={() => retry()}
              className="inline-flex h-11 items-center rounded-pill bg-ink px-5 text-base font-medium text-on-dark shadow-button focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink">
              Try again
            </button>
            {/* Plain anchor on purpose: a full reload resets a broken client state. */}
            {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
            <a href="/" className="inline-flex h-11 items-center rounded-pill border border-ink px-5 text-base font-medium text-ink hover:bg-glass">
              Go to home
            </a>
          </div>
        </main>
      </body>
    </html>
  );
}
