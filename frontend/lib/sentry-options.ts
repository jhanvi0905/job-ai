// Shared Sentry options for the browser, Node and Edge runtimes.
// DSN is optional: with NEXT_PUBLIC_SENTRY_DSN unset the SDK is disabled (no-op).
import type { Breadcrumb, ErrorEvent } from "@sentry/nextjs";

export const SENTRY_DSN = process.env.NEXT_PUBLIC_SENTRY_DSN || undefined;

const SENSITIVE_HEADER = /^(authorization|cookie|set-cookie|x-api-key|apikey|x-supabase-.*)$/i;
const BEARER = /Bearer\s+[A-Za-z0-9._~+/=-]+/g;
const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;

function scrubString(s: string): string {
  return s.replace(BEARER, "Bearer [Filtered]").replace(EMAIL, "[email]");
}

/** Strip request bodies, cookies, auth headers and query strings; mask tokens and emails. */
export function scrubEvent(event: ErrorEvent): ErrorEvent {
  if (event.request) {
    delete event.request.data;
    delete event.request.cookies;
    delete event.request.query_string;
    if (event.request.headers) {
      for (const k of Object.keys(event.request.headers)) {
        if (SENSITIVE_HEADER.test(k)) delete event.request.headers[k];
      }
    }
    if (event.request.url) event.request.url = event.request.url.split("?")[0];
  }
  if (event.user) event.user = event.user.id ? { id: event.user.id } : undefined;
  if (event.message) event.message = scrubString(event.message);
  for (const ex of event.exception?.values ?? []) {
    if (ex.value) ex.value = scrubString(ex.value);
  }
  return event;
}

/** Keep navigation/fetch breadcrumbs but drop their bodies and query strings. */
export function scrubBreadcrumb(b: Breadcrumb): Breadcrumb | null {
  if (b.data) {
    delete b.data.request_body;
    delete b.data.response_body;
    delete b.data.body;
    if (typeof b.data.url === "string") b.data.url = b.data.url.split("?")[0];
    if (typeof b.data.from === "string") b.data.from = b.data.from.split("?")[0];
    if (typeof b.data.to === "string") b.data.to = b.data.to.split("?")[0];
  }
  if (b.message) b.message = scrubString(b.message);
  return b;
}

export const baseSentryOptions = {
  dsn: SENTRY_DSN,
  enabled: Boolean(SENTRY_DSN),
  environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT || process.env.NEXT_PUBLIC_VERCEL_ENV || process.env.NODE_ENV,
  sendDefaultPii: false,
  tracesSampleRate: 0.05,
  // Only same-origin requests get trace headers: the product API and Supabase don't
  // allow sentry-trace/baggage in CORS, and adding them would break preflights.
  tracePropagationTargets: [/^\/(?!\/)/],
  beforeSend: scrubEvent,
  beforeBreadcrumb: scrubBreadcrumb,
};
