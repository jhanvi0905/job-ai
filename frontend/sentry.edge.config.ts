// Edge runtime Sentry init (proxy.ts runs here), loaded from instrumentation.ts.
import * as Sentry from "@sentry/nextjs";
import { baseSentryOptions } from "@/lib/sentry-options";

// Same DSN as the browser (NEXT_PUBLIC_SENTRY_DSN). The backend's SENTRY_DSN is
// deliberately not read here so the two projects never mix.
Sentry.init({
  ...baseSentryOptions,
});
