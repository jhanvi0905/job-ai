// Server-side instrumentation: load the Sentry config for the active runtime.
import * as Sentry from "@sentry/nextjs";

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") await import("./sentry.server.config");
  if (process.env.NEXT_RUNTIME === "edge") await import("./sentry.edge.config");
}

// Reports errors thrown while rendering Server Components, route handlers and proxy.
export const onRequestError = Sentry.captureRequestError;
