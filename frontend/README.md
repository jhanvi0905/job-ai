# Fitwise web app

The customer-facing frontend for Fitwise (landing page, auth, onboarding, feed, tracker, tailoring) plus the internal admin console. Next.js 16 App Router, React 19, Tailwind CSS 4, Supabase Auth, Sentry. Deploys to Vercel.

> Next.js 16 has breaking changes from older versions (for example `proxy.ts` replaces `middleware.ts`, and error boundaries get `retry`). Read `node_modules/next/dist/docs/` before changing framework-level code. See `AGENTS.md`.

## Quick start

```bash
cd frontend
npm ci
cp ../.env.example .env.local   # then fill in the NEXT_PUBLIC_* values below
npm run dev                     # http://localhost:3000
```

The product API (`scripts/product/run_api.py`, port 8100) must be running for signed-in pages. Without Supabase env vars the marketing site and legal pages still work; auth pages show a "not configured" notice and app routes redirect to `/login`.

## Scripts

| Script | What it does |
|---|---|
| `npm run dev` | Dev server with Turbopack on :3000 |
| `npm run build` | Production build (also uploads source maps to Sentry when `SENTRY_AUTH_TOKEN` is set) |
| `npm run start` | Serve the production build |
| `npm run lint` | ESLint (`eslint-config-next`) |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run test:e2e` | Playwright smoke suite in `e2e/` (reuses a running dev server locally; set `CI=1` to use `npm run start`) |

First Playwright run: `npx playwright install chromium`. The suite needs no Supabase and no backend: it only covers signed-out flows (landing, CTA → `/signup`, `/feed` → `/login`, legal pages, 404, security headers, 390px overflow) and fails on any CSP violation or uncaught page error. To run against a deployed preview: `E2E_BASE_URL=https://… npm run test:e2e`.

## Environment variables

All `NEXT_PUBLIC_*` values are inlined into the client bundle **at build time**, so set them before `npm run build` (in Vercel: Project → Settings → Environment Variables, then redeploy). The CSP in `next.config.ts` is also built from them.

| Variable | Required | Example | Purpose |
|---|---|---|---|
| `NEXT_PUBLIC_PRODUCT_API_URL` | yes (prod) | `https://api.fitwise.app` | Customer API base URL. Default `http://localhost:8100`. Added to CSP `connect-src`. |
| `NEXT_PUBLIC_SUPABASE_URL` | yes (prod) | `https://xyz.supabase.co` | Supabase project URL (auth). Added to CSP `connect-src` (https + wss). |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | yes (prod) | `eyJ…` | Supabase anon key. Safe to expose; every product table denies it via RLS. |
| `NEXT_PUBLIC_SITE_URL` | recommended | `https://fitwise.app` | Canonical URL for metadata / Open Graph. Default `http://localhost:3000`. |
| `NEXT_PUBLIC_SENTRY_DSN` | optional | `https://key@o1.ingest.us.sentry.io/2` | Enables Sentry in browser, Node and Edge. Unset = Sentry is a no-op. Its ingest host is added to CSP. Use a separate Sentry project from the backend's `SENTRY_DSN`. |
| `NEXT_PUBLIC_SENTRY_ENVIRONMENT` | optional | `production` | Sentry environment tag. Falls back to `NEXT_PUBLIC_VERCEL_ENV`, then `NODE_ENV`. |
| `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT` | optional (build) | | Source-map upload during `next build`. Without the token, upload is skipped. Keep the token secret (Vercel: not exposed to the browser). |
| `NEXT_PUBLIC_LEGAL_EMAIL` | before launch | `privacy@fitwise.app` | Contact address shown on `/privacy` and `/terms`. |
| `NEXT_PUBLIC_API_BASE` | admin only | `http://localhost:8000` | Single-user admin console API (`/admin`). Not needed for the product on Vercel. |

Supabase Auth settings: add `https://<your-domain>/auth/callback` (and the Vercel preview pattern) to **Redirect URLs**.

## App structure

```
app/
  layout.tsx              Root: fonts (self-hosted via next/font), globals.css, metadata
  global-error.tsx        Last-resort error boundary (reports to Sentry)
  not-found.tsx           Friendly 404
  (marketing)/            Public site: landing page (/), /privacy, /terms
  (auth)/                 /login, /signup, /forgot-password, /reset-password, /auth/callback, /auth/continue
  (app)/                  Signed-in product: /onboarding, /feed, /jobs/[id], /jobs/[id]/tailor, /tracker, /settings
  admin/                  Internal single-user console (separate API, not linked from the product)
components/
  marketing/              Landing sections (Grovia design system, docs/design/GROVIA_SPEC.md), LegalPage layout
  app/                    Product UI. ui.tsx = design-system primitives (buttons, cards, ErrorNotice…)
    hooks.ts              useLoad: fetch-on-mount with reload()
    useTask.ts            useTask / usePersistentTask: poll GET /tasks/{id} for background jobs
lib/
  product-api.ts          Typed customer API client (bearer token from the Supabase session, error mapping)
  product-types.ts        API types (mirror src/jobai/product/api on the backend)
  supabase/               Browser / server / proxy Supabase clients
  sentry-options.ts       Shared Sentry options + PII scrubbing
proxy.ts                  Next 16 proxy: refreshes the Supabase session, guards app routes
instrumentation*.ts, sentry.*.config.ts   Sentry wiring (client, Node, Edge)
e2e/                      Playwright smoke tests
```

### Background tasks

Long operations run as backend tasks: `POST /feed/refresh` → `202 {task_id}` and `POST /resume` → `201 {resume, task_id}`. `usePersistentTask(key)` polls `GET /tasks/{id}` with backoff (1s → 5s), pauses while the tab is hidden, resumes on focus, aborts on unmount, and stores the in-flight id in `sessionStorage` so a reload keeps polling. The feed shows queued/running progress and the run summary; onboarding shows "Reading your resume…" and loads achievements when the parse succeeds. Failures offer a retry.

### Errors

`ApiError` maps the backend's `{"error": {"code", "message"}}` shape. `ErrorNotice` shows:
- `429 rate_limited` / `budget_exceeded` → "Slow down a moment" (uses `Retry-After` when the API exposes it)
- `429 quota_exceeded` → plan-limit upgrade prompt
- `402` → out of credits; `502` → model failure, nothing charged; `401` → signs out and goes to `/login`

## Security

`next.config.ts` sets on every route: a Content-Security-Policy (`default-src 'self'`; `connect-src` limited to self, the product API, the admin API, Supabase https/wss and the Sentry ingest host; `frame-ancestors 'none'`; `object-src 'none'`), `Referrer-Policy: strict-origin-when-cross-origin`, a restrictive `Permissions-Policy`, `X-Content-Type-Options`, `X-Frame-Options: DENY`, and HSTS in production. Scripts use `'unsafe-inline'` because most pages are statically rendered (no per-request nonce); `'unsafe-eval'` is added in development only. If you add a third-party script or API, add its origin to the CSP or the browser will block it (the e2e suite fails on CSP violations).

Sentry: `sendDefaultPii: false`, `tracesSampleRate: 0.05`, no session replay. Request bodies, cookies, query strings and auth headers are stripped, and bearer tokens and emails in messages are masked (`lib/sentry-options.ts`).

## Deploying to Vercel

1. Import the repo in Vercel and set **Root Directory** to `frontend`. The framework preset (Next.js) and `npm run build` are detected automatically; no `vercel.json` is needed.
2. Add the environment variables above for Production (and Preview, pointing at a staging API/Supabase if you have one).
3. On the backend, allow the Vercel domain(s) in CORS, and expose `Retry-After` (`Access-Control-Expose-Headers: Retry-After`) so the rate-limit message can show the wait.
4. In Supabase Auth, add the production and preview `/auth/callback` URLs.
5. Deploy. Check the response headers on `/` and run `E2E_BASE_URL=https://<deployment> npm run test:e2e` against the preview.

Docker (self-hosting): `docker compose up web` builds this folder with the `NEXT_PUBLIC_*` build args from the root `.env`.
