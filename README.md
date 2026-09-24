# LifeOS Job Agent

Finds remote AI/ML/data engineering jobs you can work from India, has an AI
vet each one against your real achievements, and writes **only the ones worth
your time** into the Notion **Job Pipeline** (`Life OS / Domains / Job Search`).
Review them in the **Jobs to Review** view.

## How a job gets into your queue

```
49 sources ──► Stage 0: free, offline filters ──► dedup ──► Stage 1: AI triage ──► Stage 3: AI match ──► Notion
(ATS boards +   remote & India-eligible            by ID and   role type + stack       per-requirement        only approved
 Himalayas       posted ≤ 30 days                  by company  fit; can't wave         evidence check,        jobs, ranked
 newest-first)   years ask ≤ 6 (regex)             + title     through non-eng         fit computed in code   P1/P2
                 not Director/Staff/Principal
                 title has an AI/ML/data signal
```

* **Nothing is written to Notion unless the AI approves it.** If the AI is
  unreachable a job is skipped and retried next run — never written unvetted.
* **Years are code, not vibes.** Regex extracts what a posting asks for; the
  fit is capped by rule (asks within 1 yr of yours: no penalty; +2-3: at most
  plausible; +4: at most weak; 7+ never reaches the AI). The LLM never sees
  your years — it applied them inconsistently.
* **Fit is arithmetic.** The model only says, per requirement, whether your
  evidence is direct / adjacent / none. Code computes the band, priority and
  gaps from that. Final band = the lower of Stage 1 and Stage 3.
* **Duplicates:** one bulk Notion read builds in-memory indexes; a job is a
  duplicate if the ID matches *or* the company+title matches (same role via
  another source, or re-posted). Pages you've moved past "Discovered" are never
  touched.
* **Zero repeat spend:** a rejected, unchanged posting is remembered locally
  (`data/decisions.jsonl`) and costs 0 tokens. The memory self-invalidates when
  your profile, gates, prompts or models change.
* A typical daily run: ~1 min, ~$0.02.

## Commands

```bash
python scripts/sync_jobs.py             # the daily run (cron does this at 8am)
python scripts/sync_jobs.py --dry-run   # preview: what would be written / rejected and why
python scripts/rebuild_queue.py         # re-judge the whole existing queue under current rules (plan only)
python scripts/rebuild_queue.py --apply # execute that plan; trash is recoverable, only untouched automation pages
python scripts/verify_models.py         # confirm the configured AI models work
python -m pytest                        # 225 tests, offline, $0
```

## Tuning it (all config, no code)

| I want to… | Edit |
|---|---|
| Change my years / seniority cutoffs / recency | `config/career_rules.yaml` → `experience:`, `seniority:`, `recency:` |
| Target another country (e.g. Canada) | `career_rules.yaml` → `location.candidate_country` |
| Allow on-site/hybrid again | `career_rules.yaml` → `location.allowed_workplace_types` |
| Be stricter/looser on what the AI lets through | `career_rules.yaml` → `ai_gates` |
| Add a company | `config/sources.yaml` (Greenhouse / Lever / Ashby / SmartRecruiters token) |
| Add a Himalayas search | `config/sources.yaml` (`type: himalayas`, `identifier: "country=IN&q=...&sort=recent"`) |
| Update who I am to the AI | `config/candidate_profile.yaml` (summary + baseline skills) |
| Add a new achievement | `data/achievements_index.yaml` (mirrors the Master Achievement Bank, A01-A10 today) |
| Swap the AI provider/model | `config/models.yaml` (any OpenAI-compatible endpoint) |

## What the Notion columns mean

Populated by the pipeline: **Opportunity** (title — company), **Priority**
(P1 strong / P2 plausible), **Fit Band**, **Role Family** (RF01-RF04),
**Seniority** (fixed vocabulary), **Work Mode**, **Location**, **Date Posted**
(true first-published date), **Why It Fits** (one sentence), **Gaps** (only
requirements the AI found unsupported, plus any years shortfall),
**Matched Achievements**, **Strong/Partial Evidence**, **Source Channel**
(Company Careers vs Other for aggregators), **Job URL**.
Internal (hidden in the review view): Job Fingerprint, JD Hash, External Key,
Last Checked/Analysed. Yours to use: Status, Notes, Contact, Resume Version,
Applied Date, Next Follow-up, Tasks.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env   # NOTION_API_KEY (integration shared with the Job Pipeline DB), AIMLAPI_KEY
```

Scheduling: local cron runs `scripts/sync_jobs.py` daily at 8:00 (Mac must be
awake). A GitHub Actions workflow is included but needs you to push the repo
and add the three secrets yourself.

## Layout

```
config/    career_rules · candidate_profile · roles · sources · models  (behaviour lives here)
prompts/   classify_job_v2 · analyse_match_v3   (versioned; changes invalidate the rejection memory)
data/      achievements_index.yaml · decisions.jsonl (local, gitignored) · ai_usage.jsonl
src/
  sources/       one adapter per ATS + Himalayas aggregator
  jobs/          normalize · filters (Stage 0) · experience (years regex) · fingerprint/content_key · decisions
  ai/            provider · classifier (Stage 1) · matcher (Stage 3, scored in code)
  achievements/  deterministic retrieval over the compact index
  integrations/  notion (bulk read, archive) · job_record (columns ↔ meaning)
  workflows/     process_job (the pipeline)
  capabilities.py  discover_jobs / analyse_job / get_priority_jobs  (callable by a future LifeOS agent)
```

## Cost safety and observability (Phase 1)

Every model call goes through ONE gateway (`src/ai/provider.py`); no stage can
build its own unbudgeted client (provider is a required argument).

* **Retries:** exponential backoff with full jitter, transient failures only
  (timeout, connection, 429, 5xx, unparseable output); honours `Retry-After`;
  4xx never retried; one schema-repair retry that shows the model its error.
* **Budgets** (`config/models.yaml -> budget`), checked BEFORE every HTTP
  attempt: per-run $0.15, per-day $0.30 (across runs), 400-call backstop. A
  blocked call makes no request. A normal run costs ~$0.02-0.04.
* **Circuit breaker:** 5 consecutive failed calls stop all calls for the run.
* **Fail closed, never silent:** a call that can't complete leaves the job
  un-written and un-remembered, so it is retried next run. A budget stop or an
  outage is never recorded as a "rejection".
* **Ledger** (`data/ledger.db`, SQLite): every HTTP attempt with tokens, cost,
  latency, resolved model version and a closed-vocabulary outcome; every run
  with status (`ok` / `degraded` / `failed`), code version and config signature.

```bash
python scripts/health.py     # tripwires over the last 24h; exit 1 if CRITICAL. Read-only, free.
```

### Item-level events and self-audit (Phase 2)

Beyond model calls, the ledger records what happened to every *item* (job):

* **Funnel** (aggregate): every job entering Stage 0 is counted once under a
  closed-vocabulary reason (`stale`, `generic_title`, `years_too_high`,
  `location_restricted`, ..., `passed_stage0`).
* **Events** (per item, from dedup onward): each item gets exactly ONE terminal
  event per node (`dedupe`, `triage`, `match`, `write`) with a disposition
  (`passed` / `rejected` / `skipped` / `deferred` / `errored`) and a reason code.
  A duplicate terminal event is refused by a unique index.
* **Deferred != rejected.** Budget stops, breaker trips and the deep-match cap
  are recorded as `deferred` (retried next run) and never enter the rejection
  memory. The cap used to be a silent drop; it is now an explicit event.
* **Conservation:** every run audits itself. Stage 0 must account for every
  fetched job, and dedupe -> triage -> match -> write must balance item by item.
  A violation marks the run `degraded` and names the missing items.

`python scripts/health.py` adds four checks that catch failures which raise no
error: `conservation` (silent item loss), `verdicts` (a stage saying the same
thing about >=95% of 20+ items — the "35/35 weak" incident), `empty_evidence`
(retrieval, not the model, is failing) and `stuck_runs`.

### Testing policy: tests never spend money
`tests/conftest.py` neutralises API keys and makes any real HTTP call raise
`LiveNetworkBlocked`; local state (ledger, usage log, rejection memory) is
redirected to a temp dir. AI behaviour is tested against scripted fakes
(`tests/fakes.py`), including outages, 429s, budget exhaustion and the circuit
breaker. The only live check is `scripts/verify_models.py` (~$0.00002), run by
hand.

## Known limits (honest)

* Priority is a soft ranking: `gpt-4o-mini` is generous, so P1 is not rare.
  Tighten `ai_gates` or switch `analyse_match` to a stronger model in
  `models.yaml` if you want sharper separation.
* Himalayas' pagination is broken (returns page 1 regardless of offset), so
  breadth comes from many `sort=recent` queries, not deep paging.
* Naukri/Instahyre/Wellfound/LinkedIn have no legitimate public API, so
  India-specific boards aren't covered.
* Location eligibility beyond the ATS metadata is read by the AI from the
  posting text (it correctly caught "You are based in Europe or the Americas"
  on postings tagged Worldwide) — a heuristic, not legal advice.
