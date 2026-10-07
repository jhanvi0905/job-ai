# LifeOS Job Agent — Architecture

This document explains how the system is built and, more importantly, *why*
it's built that way. The design brief wasn't "find some jobs" — it was "build
something that fails safely, tells you when it's wrong, and never lies to you
about what it did." Every structural decision below traces back to that.

If you're new to the codebase, read this top to bottom once. If you're
debugging something, jump to [§7 Fault Tolerance](#7-fault-tolerance--reliability-mechanisms)
or [§8 Observability](#8-observability--self-audit).

For the literal call chain (entry point → every function called, in
execution order, cited to file:line), the exact code-level definition of
each "Stage," the full guardrail inventory, and the coding conventions
actually enforced in this repo, see **[EXECUTION_FLOW.md](EXECUTION_FLOW.md)** —
this document explains *why*; that one explains *exactly what runs*.

---

## 1. The one-sentence architecture

**A linear, self-auditing pipeline** — not an autonomous agent — that pulls
job postings from public ATS APIs, filters them for free, has an LLM vet the
survivors against your actual work history, and writes only what's worth your
time to Notion. Everything the LLM touches goes through one gateway with
budgets, retries, and a circuit breaker; everything the pipeline does is
logged to a local SQLite ledger that the pipeline itself audits at the end of
every run.

```
49 sources ──► Stage 0 (free filters + dedup) ──► Stage 1 (AI triage)
                                                          │
                                                          ▼
                                              Stage 2 (achievement retrieval)
                                                          │
                                                          ▼
                                                  Stage 3 (AI deep match)
                                                          │
                                                          ▼
                                                Notion (only what's approved)
```

A second, independent pipeline reads Gmail (read-only) to auto-advance a
job's status in Notion when a rejection/interview/offer email arrives.

## 2. Why "pipeline," not "agent"

This is a deliberate, load-bearing choice, and it's the lens to view the
whole codebase through.

An *agent* decides its own next step, loops, and can take actions with
unbounded blast radius. This system is the opposite on purpose:

- **The control flow is fixed.** `src/jobai/assistant/workflows/process_job.py::run()` always
  does fetch → filter → dedupe → classify → match → write, in that order.
  Nothing decides to skip a stage or reorder itself.
- **The LLM never acts — it only judges.** The model's output is a
  structured verdict (`relevant: bool`, `fit: strong|plausible|weak|no`,
  per-requirement `evidence: direct|adjacent|none`). Code — not the model —
  decides what happens next: whether to write to Notion, what priority to
  assign, whether years-of-experience disqualify a role. See
  `src/jobai/engine/ai/classifier.py::_is_relevant()` and `src/jobai/engine/ai/matcher.py::score_match()`.
- **A future "LifeOS" agent can call this system, but this system isn't one.**
  `src/jobai/assistant/capabilities.py` exposes three plain functions
  (`discover_jobs`, `analyse_job`, `get_priority_jobs`) explicitly designed as
  the seam where a higher-level orchestrator (agentic or not) could call in —
  "the transport is someone else's problem." Nothing in this repo loops or
  re-plans.

This matters for reliability: a fixed pipeline is trivially auditable
("did every job that entered Stage 0 get exactly one terminal outcome?"),
whereas an agent's action sequence is not. Section 7 depends on this choice.

## 3. Repository layout

```
config/    Behavior lives here, not in code — edit YAML, not Python.
  career_rules.yaml     experience/seniority/location/recency rules, AI gates
  candidate_profile.yaml the "who you are" text shown to the LLM
  roles.yaml             role-family taxonomy (RF01-RF04) + title signals
  sources.yaml           one entry per company/board: ATS type + identifier
  models.yaml            provider, per-workflow model routing, budgets, pricing

prompts/   Versioned prompt text. A version bump invalidates cached verdicts
           (see §6) because it can change what the model says about a job.
  classify_job_v2.txt    Stage 1 triage prompt
  analyse_match_v3.txt   Stage 3 deep-match prompt
  classify_email_v1.txt  inbox classifier prompt

data/      Local, gitignored state.
  ledger.db              SQLite: runs, LLM calls, item events, verdicts (§7-8)
  achievements_index.yaml your compact "evidence bank" (résumé, structured)
  ai_usage.jsonl          flat cost log (secondary to the ledger)
  gmail_token.json        OAuth token for read-only inbox access

src/
  sources/       One adapter per job board: greenhouse, lever, ashby,
                 smartrecruiters, himalayas. Each returns RawJob; a shared
                 `base.py` interface keeps them interchangeable.
  jobs/          normalize (RawJob -> NormalizedJob) · filters (Stage 0) ·
                 experience (years-required regex) · fingerprint (identity) ·
                 decisions (verdict memory / anti-repeat-spend) · schemas
                 (Pydantic contracts) · refetch (re-fetch one job by id)
  ai/            provider (the ONE gateway) · classifier (Stage 1) ·
                 matcher (Stage 3, scoring done in code) · email_classifier ·
                 role_labels
  achievements/  loader + deterministic retrieval over the evidence bank
                 (keyword/tag match — no embeddings, no vector DB, no
                 non-determinism to debug)
  integrations/  notion (bulk read, create/update page, archive) ·
                 job_record (Notion columns <-> domain meaning, one place)
  ledger/        db (SQLite schema + migrations) · codes (closed vocabularies)
                 · events (item-level accounting) · conservation (the
                 self-audit) · health (tripwires) · feedback (human-outcome
                 capture)
  inbox/         gmail (read-only client) · rules (0-token classification) ·
                 matcher (email -> Notion page) · policy (status transitions)
  workflows/     process_job.py (job pipeline) · inbox.py (email pipeline) —
                 the only two places that own a full run end-to-end
  telemetry/     logging, usage (secondary JSONL cost log)
  capabilities.py the callable-function seam for a future orchestrator
  config.py      loads config/*.yaml — the only place that touches disk for config

scripts/   Entry points: sync_jobs.py (daily run), sync_inbox.py,
           rebuild_queue.py (re-judge the whole queue under current rules),
           health.py (read the ledger's tripwires), verify_models.py,
           calibration.py, gmail_auth.py

tests/     225 tests. Zero network calls (see §7.6). Fakes over real HTTP.
```

## 4. The job pipeline, stage by stage

Source of truth: `src/jobai/assistant/workflows/process_job.py`.

### Stage 0 — free, offline filtering + dedup (`src/jobai/engine/jobs/filters.py`, `stage0_filter_and_dedupe`)

Zero model calls, zero Notion round-trips. Runs against ~1,000-6,000 raw
postings a day. Rejects on:

- **Recency** — posted more than N days ago (`career_rules.yaml → recency`)
- **Location eligibility** — not workable from the candidate's country,
  reading structured location fields first (e.g. Ashby's `addressCountry`)
  and falling back to text heuristics only when structure is absent (never
  fabricated)
- **Seniority** — title contains Director/Staff/Principal-type keywords
- **Years asked** — a regex over the JD (`src/jobai/engine/jobs/experience.py`) extracts
  "5+ years" style asks; anything past the configured ceiling is dropped
  *before* the LLM ever sees it — **years are code, not vibes** (the LLM
  applied them inconsistently, so it doesn't get to)
- **Title signal** — must carry an AI/ML/data signal or match a role-family
  alias, otherwise it's almost certainly noise

Every rejection reason maps to one closed-vocabulary **reason code**
(`src/jobai/engine/jobs/filters.py::code_for_reason`), which is what makes the funnel
queryable later instead of just a pile of free-text log lines.

**Dedup** happens in the same pass, against an in-memory index built from
*one* bulk Notion read (`DedupIndex`, built once per run — this is what
turned a 20-minute run into a ~1-minute one). A job is a duplicate if:
- its fingerprint matches an existing page (same posting), or
- its `company+title` key matches (same role via a different source, or a
  repost), or
- it was already rejected, unchanged, by a prior run (`DecisionCache`, §6).

### Stage 1 — AI triage (`src/jobai/engine/ai/classifier.py`)

One structured LLM call per Stage-0 survivor: role family, seniority, role
type, `fit` (strong/plausible/weak/no), and any hard blockers. Runs
concurrently (`AI_WORKERS = 6` threads).

Critically, the model's own `relevant: true/false` opinion **is never
trusted**. `_is_relevant()` recomputes it deterministically from
`role_type`, `fit`, and `hard_blocker` against `career_rules.yaml → ai_gates`
— so the model can't talk its way around a gate by asserting relevance.
Years-of-experience fit is also re-derived in code
(`cap_fit_by_years()`): if the JD asks for more years than the regex-derived
gap allows, the fit ceiling is forced down regardless of what the model said.

### Stage 2 — achievement retrieval (`src/jobai/engine/achievements/retrieval.py`)

Deterministic, non-LLM retrieval of the top-k relevant entries from
`data/achievements_index.yaml` (your compact evidence bank), keyed by role
family and the Stage 1 `key_requirements`. Only these retrieved records —
never the full index — go into the Stage 3 prompt. This keeps cost bounded
and keeps retrieval debuggable (no embeddings/vector DB to introspect when it
misbehaves — see the `empty_evidence` health check in §8).

### Stage 3 — deep match (`src/jobai/engine/ai/matcher.py`)

The model judges **each key requirement individually** as
`direct`/`adjacent`/`none` evidence, tagged `core`/`secondary`. It does *not*
output a fit band directly. `score_match()` computes the band in code from
those per-requirement judgments (e.g. ≥70% of core requirements direct with
zero `none` → `strong`). This is the same philosophy as Stage 1: **the model
supplies facts, code supplies judgment** — "strong" always means the same
arithmetic thing, and every listed gap is a requirement the model explicitly
marked unsupported, not a vibe.

Final fit band = the *lower* of Stage 1's role/stack fit and Stage 3's
requirement-coverage fit (both stages must agree for P1), then capped again
by the years rule.

### Write (`src/jobai/assistant/integrations/notion.py`, `job_record.py`)

Only candidates that survive Stage 3 reach here. New jobs create a Notion
page; existing (previously-seen, since-changed) jobs get updated in place.
One job's write failure is caught and logged per-item — it never aborts the
batch (`write_to_notion`).

## 5. The inbox pipeline (read-only)

Source of truth: `src/jobai/assistant/workflows/inbox.py`. Separate from the job pipeline,
same philosophy. Reads Gmail (read scope only — this system cannot send,
delete, or modify email), and for each unsettled message:

```
prefilter (0 tokens, regex) → match to ONE Notion page (0 tokens) →
  rules-based classification (0 tokens) → LLM only if rules can't decide →
  status policy → Notion update
```

Two guardrails worth knowing about:
- **Role-conflict guard**: if an email's method matched a Notion page only
  by company (not company+role) and the email text names a *different* role
  than the matched page, the status change is refused
  (`src/jobai/assistant/inbox/matcher.py::role_conflict`) — added specifically because a
  same-company, different-role email had previously caused a wrong status
  update.
- **Confidence floor**: LLM classifications below `MIN_CONFIDENCE = 0.7` are
  treated as "couldn't decide" and skipped, not acted on.

Like the job pipeline, every message gets exactly one terminal ledger row
per run, and the run checks that count against how many messages it actually
looked at before declaring itself healthy.

## 6. Cost control and the anti-repeat-spend memory

Two related but distinct mechanisms:

**The LLM gateway budget** (§7) bounds spend *within* and *across* runs.

**The decision cache** (`src/jobai/engine/jobs/decisions.py`) bounds spend *across time*
for a given job: a job the AI already rejected, unchanged, costs 0 tokens on
the next run. This memory is stored in the ledger's `verdicts` table and is
keyed by `(fingerprint, description_hash)`, gated by a **rules signature** —
a hash over the candidate profile, the AI gates, both prompt files, and the
routed model names. Change *any* of those and the signature changes, so every
past rejection is silently invalidated and the job is re-judged from
scratch. This is what lets you tighten `career_rules.yaml` or bump a prompt
version without worrying about stale verdicts lingering.

## 7. Fault tolerance & reliability mechanisms

This is the part of the system built explicitly for the property you asked
about. Read `src/jobai/engine/ai/provider.py` — it's the single most important file for
understanding the reliability posture of the whole repo.

### 7.1 One gateway, no exceptions

Every model call — from either pipeline — goes through
`LLMProvider._chat()`. No stage constructs its own HTTP client; `provider`
is a required constructor argument everywhere it's used. This is what makes
every other guarantee below possible to *enforce* rather than just *hope
for* — there's no side door.

### 7.2 Retries — but only for the right failures

Exponential backoff with **full jitter**, capped, and only for outcomes
classified as transient (`RETRYABLE_OUTCOMES`: timeout, connection error,
HTTP 429, HTTP 5xx, unparseable JSON). A 4xx ("your request is malformed")
is never retried — retrying it would just waste budget on a call that can't
succeed. `Retry-After` headers are honored when present.

### 7.3 Schema-repair, not silent coercion

If the model's JSON parses but fails the caller's Pydantic validation, the
gateway does **one** repair attempt: it shows the model its own output and
the validation error, and asks for a correction. If that also fails, it's a
hard `SchemaError` — never silently coerced into a default verdict. (See
`_validate_classification` and `_validate_match`: a missing verdict field
raises rather than being read as "no".)

### 7.4 Budgets — checked before every attempt, not after

`_guard()` runs before *every* HTTP attempt (including retries) and checks,
in order: circuit breaker state → per-run spend cap → per-day spend cap
(read from the ledger, so it holds across separate `cron` invocations) →
a call-count backstop for providers that don't report cost. **A blocked call
makes no HTTP request at all** — the budget is enforced at the gate, not by
inspecting a response after paying for it.

### 7.5 Circuit breaker

Five consecutive failed calls (tracked with a thread-safe counter) trips the
breaker for the rest of the run: further calls are refused immediately
instead of burning retries into a confirmed outage.

### 7.6 Fail closed, never silent

This is the core safety property of the whole system: **a job the AI
couldn't be reached for is left un-written and un-remembered.** It is never:
- written to Notion unvetted, or
- recorded as a rejection (which would suppress it from future runs).

It's simply retried next run. Budget stops and circuit-breaker trips are
recorded as `deferred` in the item-event ledger — explicitly distinct from
`rejected` (§8) — precisely so an outage can never masquerade as "the AI
looked at this and said no."

### 7.7 Per-source isolation

`_fetch_one()` wraps each of the 49 sources individually: one board's
failure (a broken ATS token, a timeout, a malformed payload) is logged and
skipped, and every other source still runs. `write_to_notion` applies the
same per-item isolation to writes.

### 7.8 Tests never spend money

`tests/conftest.py` neutralizes API keys and makes any real outbound HTTP
call raise `LiveNetworkBlocked` — a test that "accidentally" hits a live
endpoint fails loudly instead of quietly costing money. AI behavior
(outages, 429s, budget exhaustion, the circuit breaker tripping) is
exercised against scripted fakes in `tests/fakes.py`, not real network
uncertainty. 225 tests run for $0. The only live check,
`scripts/dev/verify_models.py`, costs about $0.00002 and is run by hand.

## 8. Observability & self-audit

Reliability that isn't observable is just luck. Section 7 stops bad *calls*;
this section is what stops **silent structural failure** — the class of bug
that raises no exception and prints no error, it just quietly loses data.

### 8.1 The ledger (`src/jobai/core/ledger/db.py`)

SQLite, not Notion, for operational data — Notion is deliberately kept as
the human-facing surface only; the ledger needs joins, aggregates, and
constraints, written many times per run. Append-only: rows are historical
facts, nothing is edited in place except a run's own end status. Every
outcome column is a **closed vocabulary enforced by a CHECK constraint**
(`src/jobai/core/ledger/codes.py`) — an unrecognized value is a loud `IntegrityError`,
not a silently-growing "other" bucket.

Four tables carry the reliability story:
- `runs` — one row per invocation, `status ∈ {running, ok, degraded, failed}`
- `llm_calls` — one row per HTTP *attempt* (not per logical call — every
  retry gets its own row), with tokens, cost, latency, resolved model
  version, and outcome
- `events` — one row per **item per pipeline node**, with a
  `disposition ∈ {passed, rejected, skipped, deferred, errored}`. A unique
  index on `(run_id, item_id, node)` makes a duplicate terminal event for the
  same item **impossible to insert** — that would be a pipeline bug caught
  at the database layer, not absorbed.
- `verdicts` / `human_outcomes` — the rejection memory (§6) plus, separately,
  what a human later actually did with an approved job (for calibration).

### 8.2 Conservation checking (`src/jobai/core/ledger/conservation.py`)

At the end of every discovery run, the pipeline **audits itself**:

```
fetch.normalized  ==  sum(stage0 funnel counts)   — Stage 0 accounts for every job
stage0.passed     ==  #dedupe events
dedupe.passed     ==  #triage events
triage.passed     ==  #match events
match.passed      ==  #write events           (skipped for dry runs)
```

If any of these don't balance, an item vanished somewhere — an exception
that got swallowed, a list slice that dropped an entry, a code path that
forgot to log its outcome. This exact failure mode produces *no error and no
log line* on its own, which is precisely why it needs a dedicated check
rather than relying on exceptions to surface it. A violation marks the whole
run `degraded` and names the specific missing item IDs.

### 8.3 `scripts/assistant/health.py` — tripwires over the last 24h

Read-only, free, exits non-zero on anything critical (suitable for a cron
health check). Each finding answers "which layer is failing?":

| Finding | Layer | What it catches |
|---|---|---|
| `spend` | cost | daily budget usage vs. cap |
| `guardrails` | cost | any budget/circuit-breaker trip |
| `failure_rate` | transport | attempt failure rate over 5%/20% |
| `schema_invalid` | model output | prompt or model regression |
| `retry_rate` / `latency_p95` | provider health | degraded upstream |
| `model_drift` | silent change | provider resolved a different model version than requested |
| `runs` / `stuck_runs` | whole pipeline | failed runs; runs that started and never finished (crash) |
| `conservation` | pipeline integrity | §8.2, re-checked here across all recent runs |
| `verdicts` | calibration | a stage saying the *same thing* about ≥95% of ≥20 items — this literally happened once ("35/35 weak") and is why the check exists |
| `empty_evidence` | retrieval | Stage 3 match calls with zero retrieved achievements — a retrieval/index bug, not a model bug |
| `inbox` | email matching | application emails that matched no pipeline job |

That `verdicts` check is worth calling out: a miscalibrated model that
rejects everything produces zero exceptions and zero log errors — every
individual call "succeeded." Only a statistical check across the run catches
it, which is the whole reason it exists as a named tripwire instead of being
left to "someone will notice the queue looks empty."

## 9. Configuration philosophy

Nearly everything a user would want to tune lives in `config/*.yaml`, not in
Python: experience/seniority/location rules, which AI gates apply, which
sources to poll, which models to route each workflow to, and the candidate's
own profile text shown to the LLM. `src/jobai/core/config.py` is the single, cached
loading point (`@lru_cache`) — no module reaches into `config/` directly.
Prompts are versioned files rather than inline strings specifically so a
prompt edit can participate in the rules-signature invalidation described in
§6.

## 10. Known, acknowledged limits

Worth stating plainly rather than discovering by surprise:

- **Priority is a soft ranking**, not a hard cutoff — the currently-routed
  model (`gpt-4o-mini`) is generous, so P1 isn't rare. Tightening is a config
  change (`ai_gates`) or a model swap (`models.yaml`), not a code change.
- **Himalayas' pagination is broken upstream** (always returns page 1), so
  breadth there comes from many distinct `sort=recent` queries, not deep
  paging.
- **No coverage for boards without a legitimate public API** (Naukri,
  Instahyre, Wellfound, LinkedIn) — India-specific reach is limited to what
  ATS platforms and Himalayas expose.
- **Location eligibility beyond structured ATS metadata is a text
  heuristic**, read by the LLM from posting prose — useful (it has correctly
  caught "You are based in Europe or the Americas" on postings mistagged
  Worldwide) but not authoritative, and not legal advice.

## 11. If you're extending this system

A few invariants to preserve, because other parts of the system assume them:

- **Never let a stage bypass `LLMProvider`.** Any new AI-touching code path
  must take a `provider` argument; that's what keeps budgets/retries/circuit
  breaker universal (§7.1).
- **Never write a verdict the model asserted directly** — derive it in code
  from structured facts the model reports (§4, Stage 1/3). This is the
  pattern that keeps gates enforceable and unable to drift with model mood.
- **New pipeline node → check `Ledger` reason-code/node vocab.** Adding a
  node or reason code goes through `src/jobai/core/ledger/codes.py`; the CHECK
  constraints exist so an unlisted code fails loudly at insert time rather
  than silently succeeding as free text. Notion column ↔ meaning is
  centralized in `src/jobai/assistant/integrations/job_record.py`.
- **A new failure mode should get a `disposition`, not a swallowed
  exception** — decide up front whether it's `rejected` (a real verdict),
  `skipped` (deterministic rule), `deferred` (retry later, not a verdict), or
  `errored` (retry later, something broke). Getting `deferred` vs `rejected`
  wrong is exactly the bug class §7.6 exists to prevent.
- **Config changes to gates/profile/prompts/model routing correctly
  invalidate old verdicts automatically** (§6) — you don't need to clear
  `data/ledger.db` by hand when you tune the rules.
