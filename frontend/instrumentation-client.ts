// Browser Sentry init (Next.js instrumentation-client convention). No session replay.
import * as Sentry from "@sentry/nextjs";
import { baseSentryOptions } from "@/lib/sentry-options";

Sentry.init({
  ...baseSentryOptions,
});

// Lets Sentry name client-side navigations for the (sampled) performance traces.
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
