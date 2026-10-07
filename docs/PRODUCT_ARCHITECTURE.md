# Product architecture

## Principles
1. **Pipeline, not agents.** The matching problem is batch judgment plus a few on-demand generations. A fixed DAG keeps cost predictable and lets us prove conservation: every job considered ends in exactly one disposition.
2. **The model reports, code decides.** Fit band, gaps, years caps and relevance are computed in code from per-requirement evidence judgments.
3. **Cheap first.** Code filters → cheap triage → deeper match only for top-N or on open → tailor only on click.
4. **Fail closed.** Anything that stops an LLM call (quota, budget, breaker, schema) yields `deferred`/`errored` and is retried; it is never stored as a verdict.
5. **Tenant isolation by construction.** Everything except the job catalog carries `user_id`; routers 404 on foreign ids (tested per resource).

## Data model (`src/jobai/product/db/models.py`)
Shared: `jobs`. Per-user: `users`, `search_prefs`, `user_job_evaluations` (unique per user+job, cache keyed by `jd_hash` + `rules_sig`), `resume_versions`, `achievements`, `tailor_runs` (unique per user+`input_hash`), `applications`, `llm_calls`, `usage_counters`, `credit_ledger`. `waitlist` is pre-account. `users.auth_id` is the Supabase `auth.users.id`; the integer PK stays the foreign key everywhere. `erased_accounts` holds tombstoned auth ids so a still-valid token can't re-create an erased account.

## Hosting
- **Supabase** provides Postgres (`DATABASE_URL` = transaction pooler, port 6543; migrations use `DIRECT_DATABASE_URL`, port 5432), Auth and Storage (private bucket `resumes`, keys `{user_id}/{uuid}-{name}`). `pgvector` is enabled by migration 0002 and not used yet.
- **FastAPI** (`src/jobai/product/api`) runs on a container host (Fly.io / Render / Cloud Run) using the same Dockerfile; the matching pipeline and LLM gateway stay in Python. Next.js deploys separately.
- **Auth flow:** the browser signs up / logs in with Supabase (email+password, magic link, Google) and keeps the session in cookies. Every API call sends `Authorization: Bearer <Supabase access token>`. `services/auth.py` verifies it locally against the project JWKS (ES256/RS256, cached 10 min; legacy HS256 via `SUPABASE_JWT_SECRET`), checks `aud=authenticated`, `iss={SUPABASE_URL}/auth/v1` and `exp`, then maps `sub` to `users` (created on first sight; a legacy row with the same email is linked). There are no signup/login routes in the API.
- **Erasure:** `DELETE /me` deletes owned rows, files (Storage prefix `{user_id}/`) and then the Supabase auth user via the Admin API with `SUPABASE_SERVICE_ROLE_KEY`; if that call fails the request is 502 and the DB transaction rolls back, so it is safely retryable.
- **Offline dev and tests:** without `SUPABASE_URL` uploads go to `UPLOAD_DIR`, the Admin call is skipped and authenticated routes return 401. Tests inject a verifier backed by a locally generated EC key, so nothing touches the network.

## Row-level security (must-do on Supabase)
Supabase exposes the `public` schema through its auto-generated Data API to anyone holding the anon key. The API connects as the table owner and enforces tenancy in code, so every table has **RLS enabled with no policies** (deny-all for `anon`/`authenticated`). Migration 0002 does this for every table, `alembic_version` included; a new table must do the same in its own migration and list itself in that migration's `RLS_TABLES` (a test fails otherwise). Check after every deploy: `curl "$SUPABASE_URL/rest/v1/users" -H "apikey: $ANON_KEY"` must return `[]` or a permission error, never rows. The service-role key bypasses RLS and must never reach the browser.

## Flow
- **Ingest** (`services/catalog.py`): existing source adapters → normalize → upsert by fingerprint; jobs unseen 14 days go inactive; one failing source never fails the run.
- **Evaluate** (`services/evaluation.py`): Stage 0 with `rules_from_prefs(prefs)` → cache check → Stage 1 (quota `triage`) → Stage 3 for top-N (quota `deep_match`). Quota is refunded if the call fails.
- **Tailor** (`services/tailor.py`): retrieve top-k achievements → LLM proposes rewrites citing evidence ids → code drops any bullet that cites unknown evidence or introduces numbers absent from the sources.
- **Gateway** (`src/jobai/engine/ai/provider.py`, `services/llm.py`): single choke point; usage lands in `llm_calls` with `user_id`; per-user daily USD guard.

## RAG
Not over resumes. Structured achievement retrieval stays the evidence layer. Embeddings (pgvector) are a later *prefilter* on the job catalog, added only if keyword retrieval measurably misses obvious matches or Stage 1 volume costs too much.

## Models and cost
Routing lives in `config/models.yaml` (`classify_job`, `analyse_match`, `parse_resume`, `tailor_resume`). Verify slugs with `scripts/dev/verify_models.py` before a real run.

## Known limitations
- Role taxonomy and gates (`allowed_role_types`, title signals) are still AI/ML-specific; per-user taxonomies are the next generalisation.
- `/feed/refresh` and resume parsing are synchronous; move to a worker before real traffic.
- Linking a Supabase identity to a legacy row by email assumes Supabase only issues tokens for confirmed emails: keep "Confirm email" on in the Supabase Auth settings.
- Supabase free projects pause when idle and have no backups; move to a paid plan before public beta.
- No payment provider yet; the credit ledger and signed webhook are the integration port.
- `config/models.yaml` has no `pricing` table, so USD guards depend on the provider reporting cost; verify before launch.

## Go-to-market (summary)
Dogfood on Canada prefs → 10 beta users → waitlist landing → Product Hunt / LinkedIn with before/after tailored bullets (not "AI agent"). Free tier: limited feed, one parse, one tailor. Pro: daily refresh and more tailors; credits for overage. Never sell JD or candidate data.
