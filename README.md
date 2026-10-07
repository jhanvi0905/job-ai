# job-ai

See which jobs actually match your work, and tailor a resume per job description **without inventing experience**.

A multi-tenant job-matching product built on a cost-disciplined LLM pipeline. It is deliberately *not* an autonomous agent: the model reports structured facts, and code decides what happens next.

```
Public ATS APIs ──► shared job catalog (fetched once for everyone)
                          │
        per user:  Stage 0 code filters (location, years, seniority, recency)   free
                          ▼
                   Stage 1 cheap LLM triage  (role family, blockers, requirements)
                          ▼
                   Stage 2 evidence retrieval from the user's own achievement bank
                          ▼
                   Stage 3 deep match (top-N/day or on job open); fit band computed in code
                          ▼
                   On-demand resume tailor: bullets must cite a real achievement, else dropped
```

## What it does (MVP)

- Upload a resume → structured, editable **achievement bank** (the only source tailored bullets may draw from)
- Per-user search prefs: countries (Canada first), remote/hybrid, role families, seniority, years
- Personalised **feed** with fit band, why it fits, and gaps; apply happens on the employer's site
- **Tailor** bullets for one job, accept per bullet, export DOCX; results cached by `(resume, JD, prompt, model)`
- **Tracker**: saved → tailored → applied → interview → offer / rejected
- Per-plan daily caps, credit ledger for overage, erasure (`DELETE /me`)

Out of scope on purpose: auto-apply, LinkedIn/Indeed scraping, multi-agent "swarms".

## Why it is built this way

| Decision | Reason |
|---|---|
| Fixed pipeline, not agents | Cheaper, testable, auditable; every job gets a terminal disposition |
| Fit is arithmetic | LLM judges per-requirement evidence; code computes band, gaps, caps |
| Fail closed | Budget/quota/LLM failure → `deferred`/`errored`, never stored as a rejection |
| One LLM gateway | Budget checked before every HTTP attempt, schema repair once, circuit breaker, per-user daily $ guard |
| Shared catalog, per-user evaluations | Ingest cost is O(sources), not O(users) |
| Structured retrieval, not RAG, over the resume | Vector search over a PDF invents bullets; typed achievements don't |

Details: [docs/PRODUCT_ARCHITECTURE.md](docs/PRODUCT_ARCHITECTURE.md). The original single-user (Notion/Gmail) pipeline this grew from is documented in [docs/single-user/](docs/single-user/README.md).

## Layout

```
src/jobai/
  core/        config loading, repo paths, run ledger, telemetry          (shared infrastructure)
  engine/      sources · jobs (normalise, Stage 0 filters) · ai (gateway, triage, match) · achievements
               the matching library: user-agnostic, parameterised per call
  product/     multi-tenant SaaS: db (models) · services · api (FastAPI) · worker
  assistant/   the original single-user LifeOS pipeline: Notion sync, Gmail inbox, orchestrator, ops API
frontend/      Next.js: landing, onboarding, feed, job, tailor, tracker, settings; ops UI under /admin
migrations/    Alembic (Postgres in production, SQLite in tests)
config/        behaviour as data: filters, role families, sources, model routing and prices
prompts/       versioned prompts; changing one invalidates cached verdicts
scripts/       product/ (api, worker, ingest) · assistant/ (daily sync, inbox, ops) · dev/ (model checks)
tests/         mirrors src: core/ engine/ product/ assistant/; offline, live network blocked
docs/          architecture, runbook-style docs, go-to-market, design spec, LLM provider research
```

Dependency rule: `core` ← `engine` ← `product` / `assistant`. The product never imports the assistant, and the engine never imports either.

## Run it

```bash
cp .env.example .env            # set AIMLAPI_KEY + SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY (and NEXT_PUBLIC_SUPABASE_*)
make setup                      # venv + deps
make migrate                    # alembic upgrade head
make ingest                     # fill the shared catalog
make api                        # http://localhost:8100  (docs at /docs)
make web                        # http://localhost:3000
make test                       # backend, offline, $0
docker compose up              # Postgres + API + web
```

## Roadmap

1. Canada dogfood, then 10 beta users
2. Embedding prefilter (pgvector) once Stage 1 volume or cost warrants it
3. Payment provider behind the existing webhook/credit port
4. Background worker for refresh and ingest
5. Optional chat/MCP front-end over the same capabilities

MIT licensed. See [CONTRIBUTING.md](CONTRIBUTING.md).
