import type { NextConfig } from "next";
import path from "node:path";
import { withSentryConfig } from "@sentry/nextjs/config";

const isDev = process.env.NODE_ENV === "development";

/** Origin of a URL env var, or null when unset/invalid. */
function origin(v: string | undefined): string | null {
  if (!v) return null;
  try { return new URL(v).origin; } catch { return null; }
}

const productApi = origin(process.env.NEXT_PUBLIC_PRODUCT_API_URL ?? "http://localhost:8100");
const adminApi = origin(process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000");
const supabase = origin(process.env.NEXT_PUBLIC_SUPABASE_URL);
const supabaseWs = supabase ? supabase.replace(/^http/, "ws") : null; // realtime / auth websockets
// Sentry ingest: the DSN host (e.g. o123.ingest.us.sentry.io) when set.
const sentryDsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
const sentryIngest = sentryDsn ? origin(sentryDsn.replace(/\/\/[^@/]*@/, "//")) : null;

const connectSrc = ["'self'", productApi, adminApi, supabase, supabaseWs, sentryIngest].filter(Boolean);
// Only upgrade when every API we call is already https (local http APIs would break).
const allHttps = [productApi, adminApi, supabase].every((o) => !o || o.startsWith("https://"));

// No nonces: most pages are static, so scripts need 'unsafe-inline' for Next's inline
// bootstrap (see docs: "Content Security Policy > Without Nonces"). Fonts are
// self-hosted by next/font, so no Google domains are needed.
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' blob: data:",
  "font-src 'self' data:",
  `connect-src ${connectSrc.join(" ")}`,
  "worker-src 'self' blob:",
  "frame-src 'none'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  ...(allHttps && !isDev ? ["upgrade-insecure-requests"] : []),
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()",
  },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  ...(isDev ? [] : [{ key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" }]),
];

const nextConfig: NextConfig = {
  poweredByHeader: false,
  turbopack: {
    root: path.join(__dirname),
  },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

// Source maps upload only when SENTRY_AUTH_TOKEN/ORG/PROJECT are set (CI / Vercel);
// otherwise this just wires the SDK in and stays quiet.
export default withSentryConfig(nextConfig, {
  org: process.env.SENTRY_ORG,
  project: process.env.SENTRY_PROJECT,
  authToken: process.env.SENTRY_AUTH_TOKEN,
  silent: !process.env.CI,
  widenClientFileUpload: true,
  sourcemaps: { disable: !process.env.SENTRY_AUTH_TOKEN },
  telemetry: false,
});
