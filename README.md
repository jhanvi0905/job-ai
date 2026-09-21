# LifeOS Job Agent

Discovers relevant SaaS/AI job openings, filters and matches them against
Jhanvi's Master Achievement Bank, and writes only useful opportunities into
the existing Notion **Job Pipeline** database (`Jhanvi — Life OS / Domains /
Job Search`). Full product spec: see the PRD this repo was built from.

## Status: Phase 1 complete (of 5)

| Phase | What it does | Status |
|---|---|---|
| 0 — Inspect | Read existing Notion schema, achievement bank, propose schema diff | ✅ done (diff applied to Notion) |
| 1 — One source end-to-end | Greenhouse fetch → normalize → dedupe → deterministic filter → Notion, no AI | ✅ done, tested |
| 2 — AI classification | Cheap triage (relevant / role family / hard blockers) | ✅ built, callable via `analyse_job()`, not yet run against real models |
| 3 — Achievement matching | Deterministic retrieval + deep match, evidence + gaps into Notion | ✅ built, callable via `analyse_job()`, not yet run against real models |
| 4 — More sources | Lever, SmartRecruiters | ✅ adapters built, Lever seeded (Anyscale); SmartRecruiters has no seed yet |
| 5 — Scheduling | Daily automated run | ✅ GitHub Actions workflow ready, disabled until secrets are set |

Phase 2/3 code is built and callable (`analyse_job()`, see below) but is
**not** part of the automatic `discover_jobs()` batch flow — per the spec's
own phasing (PRD §48 Rule 4 / §45 kill-criteria mindset), batch AI spend
should only turn on once you've run `scripts/verify_models.py` against your
real AI/ML API models. Until then, `analyse_job()` lets you test Stage 1-3
against one real job at a time without touching the daily discovery run.

## Setup

```bash
cd lifeos-job-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

1. **Notion**: create an internal integration at notion.so/my-integrations,
   copy its secret into `.env` as `NOTION_API_KEY`. Then open the **Job
   Pipeline** database in Notion → `•••` menu → Connections → add your new
   integration. Without this share step, API calls will 404.
2. **AI/ML API** (only needed once you enable Phase 2/3): put your key in
   `.env` as `AIMLAPI_KEY`, then run `python scripts/verify_models.py` — it
   sends one trivial request per configured model in `config/models.yaml`
   and tells you if the model slug is real before anything spends tokens on
   real job postings. The placeholder model names in `models.yaml` are NOT
   verified — check your AI/ML API dashboard and update them first.

## Running it

```bash
python scripts/sync_jobs.py
```

Prints a run summary (fetched / duplicates / filtered / written / errors —
PRD §36 format) and exits non-zero if any single source failed (other
sources still complete — see PRD §33).

## Scheduling (PRD §41 Phase 5)

**Recommendation: GitHub Actions**, not a local cron job. Reasoning, since
you asked for it to be reasoned through rather than assumed:

- **$0 recurring cost** either way, but a laptop-based cron only fires jobs
  discovered while your machine happens to be on — silently degrading the
  "check daily" guarantee the PRD promises without you noticing on ordinary
  self-employed/remote workdays where the laptop sleeps.
- GitHub Actions' free tier easily covers one ~1-2 minute job a day (2,000
  free minutes/month on a private repo; this repo can also just be public).
- Secrets management is built in (repo → Settings → Secrets → Actions) — no
  extra service to trust with your Notion/AI keys, unlike Activepieces.
- The workflow file (`.github/workflows/sync-jobs.yml`) is already committed
  and disabled-by-default in effect (it just won't fire until you push the
  repo to GitHub and add the three secrets: `NOTION_API_KEY`,
  `NOTION_JOB_PIPELINE_DB_ID`, `AIMLAPI_KEY`).
- You can still run `python scripts/sync_jobs.py` locally any time — nothing
  about the code depends on GitHub Actions specifically; it's a thin
  scheduler on top of the same entrypoint.

If you'd rather not push this to GitHub at all, `crontab -e` with a line like
`0 8 * * * cd ~/lifeos-job-agent && .venv/bin/python scripts/sync_jobs.py >> logs/cron.log 2>&1`
works identically — just less resilient to your laptop being asleep at 8am.

## Callable capabilities (`src/capabilities.py`)

Per PRD §25, three plain functions a future LifeOS master assistant can call
later — through MCP, an HTTP handler, a LangChain/LangGraph tool wrapper,
whatever transport shows up eventually. Nothing here is itself an agent: no
loop, no self-directed tool selection, just typed functions.

```python
from src.capabilities import discover_jobs, analyse_job, get_priority_jobs

discover_jobs()                          # Phase 1, zero AI calls, safe to run often
analyse_job("greenhouse:4123456")        # Stage 1+2+3 for ONE job, spends AI tokens, writes back to Notion
get_priority_jobs(limit=15)              # read-only "Jobs to Review" queue, Priority then Date Posted
```

`analyse_job` re-fetches the job's full description from its origin ATS
(`src/jobs/refetch.py`) rather than reading it back from Notion — Notion only
stores a `JD Hash` for change-detection, not the full text (PRD §5 rules out
a second duplicate-storage system, and JDs regularly exceed Notion's
rich_text limits anyway). This means `analyse_job` only works for jobs still
live on the source board; a closed posting raises `JobNotFoundError`.

## Extending

- **New source**: implement `JobSource.fetch_jobs()` (see `src/sources/greenhouse.py`),
  register it in `SOURCE_TYPES` in `src/workflows/process_job.py`, add companies to `config/sources.yaml`.
  Nothing downstream changes (PRD §10.2 / Phase 4 acceptance criterion).
- **New company**: just add a row to `config/sources.yaml` — no code change.
- **Tune filtering**: edit `config/career_rules.yaml` / `config/roles.yaml` — no code change.
- **Enable Phase 2/3**: wire `classify_job()` / `retrieve_achievements()` / `analyse_match()`
  into `run()` in `src/workflows/process_job.py` at the marked seam, and extend
  `write_to_notion()` to populate Role Family / Fit Band / evidence / gaps
  instead of the bare Stage-0 record.
- **New frozen achievement**: add an entry to `data/achievements_index.yaml`
  by hand after freezing it in the canonical docx — this file is deliberately
  not auto-parsed from the docx (PRD §7: never derive automation from an
  evolving canonical document without a human review step).

## Notion schema

The Job Pipeline database was extended (not duplicated) with: `Job
Fingerprint`, `Date Posted`, `Last Checked`, `Role Family`, `Seniority`, `Fit
Band`, `Matched Achievements`, `Strong Evidence`, `Partial Evidence`, `Gaps`,
`Why It Fits`, `JD Hash`, `Last Analysed`, plus a `Watch` option added to the
existing `Status` select. Everything else (`Opportunity`, `Company`, `Role`,
`Status`, `Priority`, `Source`, `Work Mode`, `Domain`, `Tasks`, ...) is
reused as-is.

`Matched Achievements` is stored as plain achievement-ID text (e.g. `A01,
A03`) for now, per PRD §22 — the Master Achievement Bank isn't a Notion
database yet. If it ever becomes one, swap that column for a real Notion
relation; `src/ai/matcher.py` already returns achievement IDs in a shape
that maps directly onto a relation.
