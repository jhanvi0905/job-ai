# Execution Flow, Stage Definitions, Guardrails & Conventions

This is the precise reference the architecture overview deliberately left out
of the way: **exactly** what runs, in what order, calling what, defined
where — plus the guardrail inventory and the coding conventions actually in
force in this repository (not aspirational ones).

Every claim below is cited to a real file. If a citation goes stale (a
function moves, a line shifts), trust the file over this document and update
this document, not the other way around.

---

## 1. Entry points — where execution actually begins

There is no single "main." Three independent things can start this codebase
running:

| Trigger | Command | Enters at |
|---|---|---|
| Local cron, 8am daily | `python scripts/assistant/sync_jobs.py` | `scripts/assistant/sync_jobs.py` |
| GitHub Actions, `0 13 * * *` UTC | same script, via `.github/workflows/sync-jobs.yml` | `scripts/assistant/sync_jobs.py` |
| Manual, read-only Gmail sync | `python scripts/assistant/sync_inbox.py [--dry-run] [--lookback N]` | `scripts/assistant/sync_inbox.py` |
| A future orchestrator (not built yet) | calls a Python function directly | `src/jobai/assistant/capabilities.py` |

`scripts/assistant/sync_jobs.py` (full file, 26 lines) is the literal entry point for
the job pipeline:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root importable
load_dotenv()                                    # .env -> os.environ (local runs only; CI uses real secrets)
configure_logging()                              # src/jobai/core/telemetry/logging.py
summary = run(dry_run="--dry-run" in sys.argv)   # src/jobai/assistant/workflows/process_job.py:369  <-- THE PIPELINE
print(summary.as_text())
sys.exit(1) if summary.source_errors else None   # non-zero exit surfaces partial source failures in CI
```

Everything from here down is inside `src/jobai/assistant/workflows/process_job.py::run()`.

---

## 2. The full call chain, in execution order

This is what actually happens, top to bottom, for one invocation of
`run(dry_run=False)`. Indentation = call depth. Every line names the real
function and its file.

```
run()                                              src/jobai/assistant/workflows/process_job.py:369
│
├─ load_career_rules(), load_roles()                src/jobai/core/config.py           (cached YAML loads)
│
├─ ledger = Ledger()                                src/jobai/core/ledger/db.py:154
│    └─ opens data/ledger.db, runs any pending numbered migration (db.py:38-150)
│
├─ run_id = ledger.start_run("discovery", ...)      src/jobai/core/ledger/db.py:197    (row in `runs`, status='running')
├─ provider = LLMProvider(ledger, run_id)           src/jobai/engine/ai/provider.py:87   (the ONE gateway for this run)
├─ events = Events(ledger, run_id)                  src/jobai/core/ledger/events.py:20 (item/funnel event recorder)
│
├─ notion = NotionClient()                          src/jobai/assistant/integrations/notion.py
├─ pages = notion.list_all_pages()                  ── the ONE bulk Notion read for the whole run
├─ index = DedupIndex(pages)                        src/jobai/assistant/workflows/process_job.py:81
│    └─ builds by_fingerprint{} and by_content_key{} in memory
│
├─ sync_human_outcomes(ledger, pages, run_id)       src/jobai/core/ledger/feedback.py  (best-effort; swallowed on failure)
├─ import_legacy_decisions(ledger)                  src/jobai/engine/jobs/decisions.py:100  (idempotent, no-op after first run)
├─ decisions = DecisionCache(ledger, run_id, ...)   src/jobai/engine/jobs/decisions.py:51
│    └─ loads last-30-days verdicts from `verdicts` table into memory, keyed by fingerprint
│
├─ jobs = fetch_all(build_sources(), summary)       src/jobai/assistant/workflows/process_job.py:126
│    ├─ build_sources()                             process_job.py:95
│    │    └─ reads config/sources.yaml, instantiates one Source subclass per company
│    │       (GreenhouseSource | LeverSource | AshbySource | SmartRecruitersSource | HimalayasSource)
│    ├─ ThreadPoolExecutor(max_workers=8) over every NON-Himalayas source:
│    │    └─ _fetch_one(source, summary)            process_job.py:107
│    │         ├─ source.fetch_jobs()               src/jobai/engine/sources/{greenhouse,lever,ashby,smartrecruiters}.py
│    │         └─ normalize_job(raw)                src/jobai/engine/jobs/normalize.py:56
│    │              ├─ strip_html(), infer_workplace_type()
│    │              └─ compute_fingerprint(), compute_description_hash()   src/jobai/engine/jobs/fingerprint.py
│    └─ Himalayas source(s) run AFTER, one at a time (not in the pool) — it's an
│       aggregator with published rate limits; single-company boards are independent hosts
│
├─ events.funnel("fetch", {"normalized": N, "normalize_failed": M})
│
├─ candidates = stage0_filter_and_dedupe(...)       src/jobai/assistant/workflows/process_job.py:141   ◄── STAGE 0
│    for each NormalizedJob:
│    ├─ apply_filters(job, career_rules, roles_config)   src/jobai/engine/jobs/filters.py:120
│    │    └─ extract_required_years(job.description)     src/jobai/engine/jobs/experience.py
│    ├─ if filtered: events.item("stage0" via funnel Counter, not per-item — 6,000 items/run, aggregate only)
│    ├─ if passed: check index.by_fingerprint / by_content_key / decisions.is_known_rejection
│    └─ events.item("dedupe", fp, disposition, code)     — the first PER-ITEM event
│    events.funnel("stage0", funnel_counts)
│
├─ vetted = evaluate(candidates, decisions, career_rules, summary, provider, events)   process_job.py:228
│    │
│    ├─ ThreadPoolExecutor(max_workers=6):
│    │    └─ classify_job(candidate.job, provider)      src/jobai/engine/ai/classifier.py:24        ◄── STAGE 1
│    │         ├─ extract_required_years(job.description)     (regex fact, not model opinion)
│    │         ├─ prompt = prompts/classify_job_v2.txt.format(...)
│    │         ├─ provider._chat(model=..., validate=_validate_classification)   src/jobai/engine/ai/provider.py:117
│    │         │    └─ THE GATEWAY LOOP — see §4
│    │         ├─ cap_fit_by_years(fit, min_years_required, candidate_years)   classifier.py:69
│    │         └─ _is_relevant(raw, ai_gates)             classifier.py:80    (derives `relevant`, never trusts the model's own claim)
│    │
│    ├─ for each (candidate, verdict): events.item("triage", fp, "passed"|"rejected"|"deferred"|"errored", code)
│    │    └─ rejected → decisions.record_rejection(fp, jd_hash, reason, node="triage", code)
│    │
│    ├─ cap = career_rules["ai_gates"]["max_deep_matches_per_run"]
│    │    └─ overflow beyond cap → events.item("match", fp, "deferred", "cap_overflow")  (never silently dropped)
│    │
│    ├─ ThreadPoolExecutor(max_workers=6):
│    │    ├─ retrieve_achievements(role_family, key_requirements)   src/jobai/engine/achievements/retrieval.py    ◄── STAGE 2
│    │    │    └─ deterministic tag/keyword weighting over data/achievements_index.yaml — top-k only
│    │    └─ analyse_match(job, key_requirements, achievements, provider, classification)   src/jobai/engine/ai/matcher.py:17   ◄── STAGE 3
│    │         ├─ prompt = prompts/analyse_match_v3.txt.format(...)
│    │         ├─ provider._chat(model=..., validate=_validate_match)   src/jobai/engine/ai/provider.py:117
│    │         │    └─ THE GATEWAY LOOP — see §4 (same code path as Stage 1)
│    │         └─ score_match(raw)                       matcher.py:65   (band/priority/gaps computed in CODE, not asserted by the model)
│    │
│    └─ for each (candidate, match):
│         ├─ stage1_rank vs stage3_rank → fit_band = min(the two)      process_job.py:307-310
│         ├─ cap_fit_by_years(...) applied AGAIN post-match             process_job.py:311
│         ├─ priority = {"strong":"P1","plausible":"P2"}.get(band,"P3")
│         ├─ events.item("match", fp, "passed"|"rejected", code)
│         └─ rejected → decisions.record_rejection(...) | passed → decisions.record_approval(...)
│
├─ if not dry_run: write_to_notion(vetted, notion, summary, events)     process_job.py:335   ◄── WRITE
│    for each approved candidate:
│    ├─ base_properties(job, is_new) + evaluation_properties(classification, match)   src/jobai/assistant/integrations/job_record.py
│    ├─ notion.create_job_page(properties)  OR  notion.update_job_page(page_id, properties)
│    └─ events.item("write", fp, "passed"|"errored", code)     (one write failure never aborts the batch)
│
├─ summary.estimated_cost_usd = ledger.spent_in_run(run_id)
├─ violations = check_conservation(ledger, run_id, dry_run)     src/jobai/core/ledger/conservation.py:37
├─ status = "degraded" if (ai_errors or violations or events.write_failures) else "ok"
│    (an unhandled exception anywhere above instead sets status="failed" and re-raises)
└─ ledger.finish_run(run_id, status, note); ledger.close()
```

That's the entire pipeline. Nothing runs outside this call tree for a
discovery run — no background threads, no hidden schedulers, no state
mutated outside what's shown above.

The inbox pipeline (`scripts/assistant/sync_inbox.py` → `src/jobai/assistant/workflows/inbox.py::run()`)
follows the identical shape at smaller scale: `list_message_ids` →
`get_message` per id → `rules.looks_like_application_mail` (0 tokens) →
`match_email` (0 tokens) → `rules.classify_by_rules` (0 tokens) →
`classify_email` via the same `LLMProvider._chat` gateway only if rules
couldn't decide → `policy.decide` → `notion.update_job_page`. See
`src/jobai/assistant/workflows/inbox.py::_process()` for the literal per-message sequence.

---

## 3. What a "Stage" actually is (this is not a type in the code)

**There is no `Stage` class or enum.** "Stage N" is a naming convention from
the project's PRD, carried into module docstrings so the numbering stays
consistent across the codebase. Here is the exhaustive, authoritative
mapping — every stage cited to the exact docstring that defines it:

| Stage | Defined in (docstring) | Implementing function | Model call? | Input → Output |
|---|---|---|---|---|
| **Stage 0** | `src/jobai/engine/jobs/filters.py:1` — *"Stage 0 — deterministic filtering. Zero model calls (PRD §14)"* | `apply_filters()` in `filters.py:120`, invoked from `stage0_filter_and_dedupe()` in `process_job.py:141` | No | `NormalizedJob` → `FilterResult(passed: bool, codes: list[str])` |
| **Stage 1** | `src/jobai/engine/ai/classifier.py:1` — *"Stage 1 — AI triage (PRD §15). One structured call per Stage-0 survivor"* | `classify_job()` in `classifier.py:24` | Yes, 1 call | `NormalizedJob` → `JobClassification` (role_family, fit, hard_blocker, key_requirements) |
| **Stage 2** | `src/jobai/engine/achievements/retrieval.py:1` — *"Stage 2 — deterministic achievement retrieval (PRD §16)"* | `retrieve_achievements()` | No | `(role_family, key_requirements)` → `list[RetrievedAchievement]` (top-k) |
| **Stage 3** | `src/jobai/engine/ai/matcher.py:1` — *"Stage 3 — deep job/evidence match analysis (PRD §17)"* | `analyse_match()` in `matcher.py:17` | Yes, 1 call | `(job, key_requirements, achievements, classification)` → `JobMatch` (fit_band, priority, gaps) |

There is no "Stage 4" — the write to Notion is called exactly that, `write`,
both in code (`write_to_notion()`) and in the ledger's closed vocabulary
(`NODES = {"fetch", "stage0", "dedupe", "triage", "match", "write"}`,
`src/jobai/core/ledger/codes.py`). Note the ledger's own node names **do not match the
PRD stage numbers 1:1** — this is worth knowing so you don't go looking for
a `"stage1"` node in the database:

| PRD name | Ledger node name (what you'll actually query) |
|---|---|
| Stage 0 | `stage0` (aggregate funnel only) then `dedupe` (per-item) |
| Stage 1 | `triage` |
| Stage 2 | *(not logged as its own node — it's inline inside the `match` call)* |
| Stage 3 | `match` |
| — | `write` |

---

## 4. The gateway loop, expanded (the part every AI call goes through)

`LLMProvider._chat()` in `src/jobai/engine/ai/provider.py:117` is a single `while True:`
loop. This is its literal control flow (not paraphrased):

```
loop:
  self._guard(attempt_no, meta)          # provider.py:235 — raises BEFORE any HTTP call if:
                                          #   • circuit breaker open (5 consecutive failures this run)
                                          #   • per-run spend >= budget.per_run_usd
                                          #   • per-day spend >= budget.per_day_usd  (queried from the ledger)
                                          #   • calls this run >= budget.max_calls_per_run
  result = self._attempt(...)            # provider.py:172 — the actual HTTP POST + parse + validate
  self._record(attempt_no, meta, result) # ALWAYS logged to llm_calls, success or failure

  if result.outcome == "ok":
      self._note_success()  → resets consecutive-failure counter to 0
      return result.parsed

  if result.outcome == "schema_invalid" and not already repaired:
      append the model's own bad output + the validation error to the message list
      loop again (ONE repair attempt only, ever)

  if result.outcome in RETRYABLE_OUTCOMES:       # http_429, http_5xx, timeout, connection_error, invalid_json
      if http_attempts < gateway.max_attempts (default 3):
          sleep(full-jitter backoff, honouring Retry-After if the server sent one)
          loop again

  # anything else falls through to here:
  self._note_failure()  → increments consecutive-failure counter
  raise SchemaError(...) or LLMError(...)
```

`http_4xx` is deliberately **absent** from `RETRYABLE_OUTCOMES` — a 4xx means
the request itself is malformed, and retrying a malformed request just spends
budget to fail the same way again.

---

## 5. Guardrail inventory

Every mechanism in the system that exists specifically to bound cost, bound
blast radius, or catch a silent failure — what it does, where it lives, what
config governs it, and what it prevents.

| Guardrail | Mechanism | Location | Governed by | Prevents |
|---|---|---|---|---|
| Single gateway | `provider` is a required constructor arg everywhere an AI call is made | `src/jobai/engine/ai/provider.py` (all callers: `classifier.py`, `matcher.py`, `email_classifier.py`) | — | A stage building its own unbudgeted HTTP client |
| Per-run budget | Checked before every attempt | `LLMProvider._guard()`, `provider.py:235` | `config/models.yaml → budget.per_run_usd` (default $0.15) | Runaway spend within one run |
| Per-day budget | Same guard, reads `ledger.spent_today()` | `provider.py:249` | `budget.per_day_usd` (default $0.30) | Runaway spend across cron/CI invocations sharing one ledger |
| Call-count backstop | Same guard | `provider.py:251` | `budget.max_calls_per_run` (default 400) | Providers that don't report token cost, where $ tracking can't catch runaway calls |
| Circuit breaker | 5 consecutive failed attempts blocks all further calls this run | `provider.py:237-242`, counter in `_note_failure()`/`_note_success()` | `gateway.circuit_breaker_failures` (default 5) | Burning the retry budget into a confirmed outage |
| Retry, transient only | Backoff + full jitter; `http_4xx` never retried | `provider.py:161-169`, `codes.py: RETRYABLE_OUTCOMES` | `gateway.max_attempts`, `backoff_base_s`, `backoff_max_s` | Retrying unrecoverable errors; thundering-herd retries |
| Schema repair | One corrective retry showing the model its own validation error | `provider.py:150-159` | — (always one attempt) | Silently accepting/coercing malformed model output |
| Fail-closed on AI failure | A failed/deferred call leaves the job un-written, un-remembered | `evaluate()` in `process_job.py:255-261`, `_llm_failure()` at `process_job.py:208` | — | An outage or budget stop being recorded as a rejection (which would suppress the job forever) |
| Per-source isolation | Each source's fetch wrapped individually; one failure doesn't stop others | `_fetch_one()`, `process_job.py:107` | — | One broken ATS token/board taking down the whole run |
| Per-write isolation | Each Notion write wrapped individually | `write_to_notion()`, `process_job.py:352` | — | One malformed page blocking the rest of the batch |
| Closed-vocabulary events | DB `CHECK` constraints on every outcome/disposition/reason column | `src/jobai/core/ledger/codes.py`, enforced in `src/jobai/core/ledger/db.py` migrations | — | An unrecognized value silently growing an "other" bucket instead of erroring |
| One terminal event per item per node | `UNIQUE INDEX idx_events_terminal ON events(run_id, item_id, node)` | `src/jobai/core/ledger/db.py:86` | — | A double-counted or contradictory outcome for the same item |
| Conservation check | Item counts must balance between every consecutive stage | `src/jobai/core/ledger/conservation.py::check_conservation()` | — | An item silently vanishing (swallowed exception, truncated list) with no error raised |
| Verdict cache + rules signature | A rejection is only reused while `jd_hash` and `rules_sig` both match | `src/jobai/engine/jobs/decisions.py::rules_signature()`, `DecisionCache.is_known_rejection()` | Hash of `candidate_profile.yaml` + `ai_gates`/`experience`/`seniority` + both prompt files + routed model names | Stale verdicts persisting after you tighten/loosen rules, change the prompt, or change model |
| Years-in-code, not years-in-model | Regex extracts the ask; `cap_fit_by_years()` enforces the ceiling deterministically | `src/jobai/engine/jobs/experience.py`, `src/jobai/engine/ai/classifier.py:69` | `career_rules.yaml → experience.total_years` | The model applying years inconsistently (observed failure mode that motivated this) |
| Model-asserted relevance never trusted | `relevant` is recomputed from `role_type`/`fit`/`hard_blocker`, not read from the model | `_is_relevant()`, `classifier.py:80` | `career_rules.yaml → ai_gates` | The model waving through an out-of-scope role by simply asserting "relevant: true" |
| Test isolation from real money | Any live HTTP call in tests raises `LiveNetworkBlocked`; state redirected to temp dirs | `tests/conftest.py` | — | A test accidentally spending real API budget |
| Health tripwires | 10 read-only checks over the last 24h, `ok`/`warn`/`crit` | `src/jobai/core/ledger/health.py::check()`, run via `scripts/assistant/health.py` | — | Failures that raise no exception (miscalibration, drift, stuck runs) going unnoticed |

---

## 6. Repository & tooling understanding

**Language / runtime**: Python 3.12 (pinned in `.github/workflows/sync-jobs.yml`;
no `.python-version` file committed, so local dev should match 3.12).

**Dependencies** (`requirements.txt` — the complete list, nothing implicit):

| Package | Used for | Where |
|---|---|---|
| `requests` | The only HTTP client in the codebase | `src/jobai/engine/ai/provider.py` (model calls), `src/jobai/engine/sources/*.py` (ATS APIs), `src/jobai/assistant/integrations/notion.py`, `src/jobai/assistant/inbox/gmail.py` |
| `pydantic` (v2) | Schema validation at every boundary crossing | `src/jobai/engine/jobs/schemas.py` — `RawJob`, `NormalizedJob`, `JobClassification`, `JobMatch`, `AIUsageRecord` |
| `PyYAML` | Loads every file under `config/` | `src/jobai/core/config.py::load_yaml()` |
| `python-dotenv` | Loads `.env` for local runs only (CI injects real secrets as env vars) | `scripts/assistant/sync_jobs.py`, `scripts/assistant/sync_inbox.py` |
| `pytest` | The entire test suite (225 tests) | `tests/` |

**Storage**: SQLite via the Python standard library `sqlite3` module — no
ORM, no external database service. `data/ledger.db` is opened with
`check_same_thread=False` plus an explicit `threading.Lock()` in `Ledger`
(`src/jobai/core/ledger/db.py:159-161`) because the AI gateway is called concurrently
from a `ThreadPoolExecutor`. `PRAGMA journal_mode = WAL` is set for
concurrent-read safety.

**Schema management**: numbered, hand-written SQL migrations in a Python
dict (`MIGRATIONS` in `src/jobai/core/ledger/db.py`), applied in order inside a
transaction, tracked in a `schema_version` table. No migration framework
(Alembic etc.) — deliberately minimal, since this is one file, one process.

**External services**: Notion (job pipeline database, via its REST API
through `requests`), Gmail (read-only OAuth, via `src/jobai/assistant/inbox/gmail.py`), and
one OpenAI-compatible LLM endpoint configured in `config/models.yaml`
(currently AI/ML API, routed per-workflow — `classify_job` and
`analyse_match` can each point at a different model).

**No build step.** This is a script-run repository, not a packaged
distributable — there's no `setup.py`/build backend beyond `pyproject.toml`'s
`[tool.pytest.ini_options]` block (which only configures `pythonpath` and
`testpaths` for pytest; it does not declare a package).

---

## 7. Code conventions actually in force (observed, not aspirational)

**There is no committed linter or formatter config** — no `ruff.toml`,
`.flake8`, `pyproject.toml [tool.ruff]` section, or `.pre-commit-config.yaml`
exists in this repo. The conventions below are enforced by consistency, not
tooling, and are inferred from actual usage across `src/`:

- **`ruff`-style suppression comments are used by convention**, even without
  a committed ruff config, meaning contributors are expected to run ruff
  locally with its default rule set:
  - `# noqa: BLE001` on every bare `except Exception:` — always paired with
    a short comment explaining *why* the broad catch is intentional (e.g.
    `# noqa: BLE001 — one job's write failing must not kill the batch`,
    `process_job.py:352`). A bare except with no `noqa` and no reason should
    be treated as a bug, not a style nit.
  - `# noqa: SLF001` on the three call sites of `provider._chat()`
    (`classifier.py:41`, `matcher.py:36`, `email_classifier.py:29`) — the
    leading underscore marks it "not a public API," and the noqa comment
    explicitly says *"internal, single call site by design."* Do not call
    `_chat()` from a fourth location without asking whether it should be
    renamed public first.
  - `# noqa: E402` in the two `scripts/*.py` entry points, because
    `sys.path.insert()` must run before the `src.*` imports that follow it.
- **`from __future__ import annotations`** at the top of every module that
  uses modern type-hint syntax (`dict[str, X]`, `X | None`) — this is what
  lets the codebase target Python's built-in generic syntax without
  requiring `typing.Dict`/`Optional` even on versions where that'd normally
  need the `typing` module. Every file in `src/` follows this.
- **Line length is not enforced at 79/88** (Black's default) — lines up to
  ~130 characters appear routinely where a docstring or a chained condition
  reads better unbroken. There's no evidence of a hard wrap column; wrap for
  readability, not a rule.
- **Docstrings open with a PRD citation where one exists** (`"""Stage 0 —
  deterministic filtering. Zero model calls (PRD §14)."""`). This is a
  deliberate traceability convention — a design decision that looks
  arbitrary in isolation usually isn't, and the citation is where to find
  the reasoning. New modules that encode a non-obvious policy decision
  should keep this pattern even without a formal PRD — a one-line "why",
  not "what."
- **`dataclass` vs. Pydantic `BaseModel` is a deliberate split, not
  inconsistency**: Pydantic models (`src/jobai/engine/jobs/schemas.py`) are used
  exclusively for data that crosses a validation boundary (LLM output, raw
  source payloads). Plain `@dataclass` (`FilterResult` in `filters.py`,
  `Candidate`/`DedupIndex` in `process_job.py`, `RunSummary` in
  `telemetry/logging.py`) is used for internal wiring that's never
  serialized or externally validated. Don't reach for Pydantic where a
  dataclass will do — it signals "this crossed a boundary" when it hasn't.
- **Closed vocabularies over free strings** wherever a value will later be
  grouped or filtered on: every ledger outcome, disposition, and reason code
  is a member of a `frozenset` in `src/jobai/core/ledger/codes.py`, enforced by a SQL
  `CHECK` constraint. A new reason code is added to `codes.py` first, in the
  same commit as the code path that produces it — never introduced as an
  ad-hoc string at the call site.
- **Comments explain *why*, not *what*** — this is the dominant style
  throughout `src/`. A representative example: `# A "Remote - United States"
  style location strings rarely use prose restriction phrases — catch the
  named region directly.` (`filters.py:105-106`). Comments that restate the
  line below them essentially don't appear in this codebase; match that bar
  before adding a new one.
- **Config, never hardcoded constants, for anything a user might tune** —
  even values that look like implementation details (thread pool sizes are
  the one exception, hardcoded as `AI_WORKERS = 6` / `FETCH_WORKERS = 8` at
  the top of `process_job.py`, since they're an infra concern, not a
  behavior one). Everything behavior-facing lives in `config/*.yaml`.

---

## 8. How this document relates to the others

- **`docs/ARCHITECTURE.md`** — the narrative explanation: why the system is
  shaped this way, the philosophy behind each design choice. Read that
  first if you're new.
- **This file** — the literal reference: exact call order, exact
  citations, exact guardrail list. Read this when you need to know *where*
  something is enforced, not just *that* it is.
- **The interactive schematic artifact** — a visual, three-audience
  (business / product / engineering) tour for a non-code-reading pass. Not
  a substitute for either markdown file above.
