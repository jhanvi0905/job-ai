"""Pipeline: fetch -> Stage 0 (free filters + dedup) -> Stage 1 AI triage ->
Stage 3 AI deep match -> Notion.

The rule the whole thing is built around: **nothing reaches Notion unless the
AI has vetted it.** Notion is your review queue, not a dump.

Cost/latency discipline (PRD §2.3 / §19 — narrow before you pay):
  * Stage 0 is free and offline: location eligibility, recency, years-of-
    experience regex, too-senior titles, AI/ML/data title signal, plus dedup
    against an in-memory index built from ONE bulk Notion read (no per-job
    Notion round-trips — that was the 20-minute run).
  * Dedup is by fingerprint (same posting) AND by company+title (same role via
    another source, or re-posted), plus a local memory of AI rejections so an
    unchanged rejected JD never costs a second LLM call.
  * Stage 1 (classify) runs only on Stage-0 survivors; Stage 3 (deep match
    against your achievements) only on Stage-1 passes. Both run concurrently.
  * A job the AI can't be reached for is skipped and retried next run — never
    written unvetted.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone

from src.achievements.retrieval import retrieve_achievements
from src.ai.classifier import FIT_RANK, cap_fit_by_years, classify_job
from src.ai.matcher import analyse_match
from src.ai.provider import LLMProvider
from src.config import load_career_rules, load_roles, load_sources
from src.integrations.job_record import base_properties, evaluation_properties
from src.integrations.notion import NotionClient
from src.jobs.decisions import DecisionCache
from src.jobs.filters import apply_filters
from src.jobs.fingerprint import content_key
from src.jobs.normalize import normalize_job
from src.jobs.schemas import JobClassification, JobMatch, NormalizedJob
from src.sources.ashby import AshbySource
from src.sources.base import JobSource
from src.sources.greenhouse import GreenhouseSource
from src.sources.himalayas import HimalayasSource
from src.sources.lever import LeverSource
from src.sources.smartrecruiters import SmartRecruitersSource
from src.telemetry.logging import RunSummary
from src.telemetry.usage import estimate_run_cost

logger = logging.getLogger(__name__)

AI_WORKERS = 6
FETCH_WORKERS = 8

SOURCE_TYPES: dict[str, type[JobSource]] = {
    "greenhouse": GreenhouseSource,
    "lever": LeverSource,
    "smartrecruiters": SmartRecruitersSource,
    "ashby": AshbySource,
    "himalayas": HimalayasSource,
}
# Aggregators publish rate limits and are hit one at a time; single-company
# boards are independent hosts and safe to fetch concurrently.
_SEQUENTIAL_SOURCE_TYPES = {"himalayas"}

_MATCH_FIT_RANK = {**FIT_RANK, "blocked": 0}


@dataclass
class Candidate:
    job: NormalizedJob
    existing: dict | None  # the Notion page (plain dict) if this job is already there
    classification: JobClassification | None = None
    match: JobMatch | None = None


class DedupIndex:
    """In-memory view of the Job Pipeline, built from one bulk read."""

    def __init__(self, pages: list[dict]):
        self.by_fingerprint: dict[str, dict] = {}
        self.by_content_key: dict[str, dict] = {}
        for page in pages:
            fp = page.get("Job Fingerprint")
            if fp:
                self.by_fingerprint[fp] = page
            if page.get("Company") and page.get("Role"):
                self.by_content_key.setdefault(content_key(page["Company"], page["Role"]), page)


def build_sources() -> list[JobSource]:
    sources = []
    for company in load_sources():
        src_cfg = company["source"]
        source_cls = SOURCE_TYPES.get(src_cfg["type"])
        if source_cls is None:
            logger.warning("unknown source type '%s' for %s — skipping", src_cfg["type"], company["name"])
            continue
        sources.append(source_cls(company_name=company["name"], identifier=src_cfg["identifier"]))
    return sources


def _fetch_one(source: JobSource, summary: RunSummary) -> tuple[list[NormalizedJob], int]:
    """One source's failure must not halt the others (PRD §33). Returns
    (normalized jobs, raw count) — counting happens in the caller's thread."""
    try:
        raw_jobs = source.fetch_jobs()
    except Exception as exc:  # noqa: BLE001
        msg = f"{source.__class__.__name__}({source.identifier}): {exc}"
        logger.error("source fetch failed: %s", msg)
        summary.source_errors.append(msg)
        return [], 0
    normalized: list[NormalizedJob] = []
    for raw in raw_jobs:
        try:
            normalized.append(normalize_job(raw))
        except Exception:  # noqa: BLE001
            logger.warning("normalize failed for %s/%s", raw.source, raw.external_job_id, exc_info=True)
    return normalized, len(raw_jobs)


def fetch_all(sources: list[JobSource], summary: RunSummary) -> list[NormalizedJob]:
    sequential_classes = tuple(SOURCE_TYPES[t] for t in _SEQUENTIAL_SOURCE_TYPES)
    boards = [s for s in sources if not isinstance(s, sequential_classes)]
    aggregators = [s for s in sources if isinstance(s, sequential_classes)]

    jobs: list[NormalizedJob] = []
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        results = list(pool.map(lambda s: _fetch_one(s, summary), boards))
    results.extend(_fetch_one(s, summary) for s in aggregators)
    for batch, raw_count in results:
        jobs.extend(batch)
        summary.fetched += raw_count
    return jobs


def stage0_filter_and_dedupe(
    jobs: list[NormalizedJob],
    index: DedupIndex,
    decisions: DecisionCache,
    career_rules: dict,
    roles_config: dict,
    summary: RunSummary,
) -> list[Candidate]:
    """Free and offline: no Notion or LLM calls happen here."""
    candidates: list[Candidate] = []
    seen_fingerprints: set[str] = set()
    seen_content_keys: set[str] = set()

    for job in jobs:
        if job.job_fingerprint in seen_fingerprints:
            summary.duplicates += 1  # same posting returned by two queries in one run
            continue

        result = apply_filters(job, career_rules, roles_config)
        if not result.passed:
            summary.stale_or_filtered += 1
            logger.debug("filtered out %s @ %s: %s", job.title, job.company_name, result.reasons)
            continue
        seen_fingerprints.add(job.job_fingerprint)

        existing = index.by_fingerprint.get(job.job_fingerprint)
        if existing is not None:
            if existing.get("Status") not in (None, "Discovered"):
                summary.in_progress_skipped += 1  # you've moved it on; hands off
                continue
            if existing.get("JD Hash") == job.description_hash:
                summary.duplicates += 1
                continue
            # Same posting, changed description -> re-evaluate (PRD §12).
        else:
            key = content_key(job.company_name, job.title)
            if key in index.by_content_key or key in seen_content_keys:
                summary.content_duplicates += 1
                continue
            seen_content_keys.add(key)

        if decisions.is_known_rejection(job.job_fingerprint, job.description_hash):
            summary.previously_rejected += 1
            continue

        summary.new_candidates += 1
        candidates.append(Candidate(job=job, existing=existing))
    return candidates


def evaluate(
    candidates: list[Candidate],
    decisions: DecisionCache,
    career_rules: dict,
    summary: RunSummary,
    provider: LLMProvider | None = None,
) -> list[Candidate]:
    """Stage 1 then Stage 3, concurrent within each stage. Returns only the
    candidates the AI says are worth your time."""
    if not candidates:
        return []
    provider = provider or LLMProvider()
    gates = career_rules["ai_gates"]

    def _classify(c: Candidate):
        try:
            return classify_job(c.job, provider)
        except Exception as exc:  # noqa: BLE001
            return exc

    with ThreadPoolExecutor(max_workers=AI_WORKERS) as pool:
        verdicts = list(pool.map(_classify, candidates))

    passed: list[Candidate] = []
    for cand, verdict in zip(candidates, verdicts):
        if isinstance(verdict, Exception):
            # Fail CLOSED: never write an unvetted job. Not recorded as a
            # rejection, so the next run retries it.
            summary.ai_errors.append(f"classify {cand.job.job_fingerprint}: {verdict}")
            continue
        summary.classified += 1
        cand.classification = verdict
        if not verdict.relevant:
            summary.ai_rejected += 1
            reason = f"stage1 {verdict.role_type}/{verdict.fit}: {verdict.why}"
            summary.rejections.append(f"{cand.job.title} @ {cand.job.company_name} -> {reason}")
            decisions.record_rejection(cand.job.job_fingerprint, cand.job.description_hash, reason)
            continue
        passed.append(cand)

    cap = gates["max_deep_matches_per_run"]
    if len(passed) > cap:
        logger.warning("%d jobs passed Stage 1; deep-matching the first %d, rest next run", len(passed), cap)
        passed = passed[:cap]

    def _match(c: Candidate):
        try:
            cls = c.classification
            achievements = retrieve_achievements(cls.role_family, cls.key_requirements)
            return analyse_match(c.job, cls.key_requirements, achievements, provider, cls)
        except Exception as exc:  # noqa: BLE001
            return exc

    with ThreadPoolExecutor(max_workers=AI_WORKERS) as pool:
        matches = list(pool.map(_match, passed))

    final: list[Candidate] = []
    min_rank = FIT_RANK[gates["min_match_fit"]]
    for cand, result in zip(passed, matches):
        if isinstance(result, Exception):
            summary.ai_errors.append(f"match {cand.job.job_fingerprint}: {result}")
            continue
        summary.deeply_analysed += 1
        # Same years rule as Stage 1, enforced in code; Priority always follows
        # the final band so the two columns can't contradict each other.
        # Final band = the LOWER of Stage 1 (role/stack/scope fit) and Stage 3
        # (requirement coverage): P1 needs both stages to agree. Years cap last.
        stage1_rank = FIT_RANK.get(cand.classification.fit or "plausible", 2)
        stage3_rank = _MATCH_FIT_RANK.get(result.fit_band, 0)
        if stage3_rank > 0:
            result.fit_band = {1: "weak", 2: "plausible", 3: "strong"}[min(stage1_rank, stage3_rank)]
        result.fit_band = cap_fit_by_years(
            result.fit_band, cand.classification.min_years_required, career_rules["experience"]["total_years"]
        )
        result.priority = {"strong": "P1", "plausible": "P2"}.get(result.fit_band, "P3")
        if _MATCH_FIT_RANK.get(result.fit_band, 0) < min_rank or result.recommended_action == "reject":
            summary.match_rejected += 1
            reason = f"stage3 {result.fit_band}: {result.reason}"
            summary.rejections.append(f"{cand.job.title} @ {cand.job.company_name} -> {reason}")
            decisions.record_rejection(cand.job.job_fingerprint, cand.job.description_hash, reason)
            continue
        cand.match = result
        summary.approvals.append(
            f"[{result.priority} {result.fit_band}] {cand.job.title} @ {cand.job.company_name}"
            f" ({cand.classification.seniority}) — {result.reason}"
        )
        final.append(cand)
    return final


def write_to_notion(candidates: list[Candidate], notion: NotionClient, summary: RunSummary) -> None:
    for cand in candidates:
        is_new = cand.existing is None
        properties = {
            **base_properties(cand.job, is_new=is_new),
            **evaluation_properties(cand.classification, cand.match),
        }
        try:
            if is_new:
                notion.create_job_page(properties)
            else:
                notion.update_job_page(cand.existing["notion_page_id"], properties)
            summary.written_to_notion += 1
        except Exception as exc:  # noqa: BLE001 — one job's write failing must not kill the batch
            msg = f"Notion write failed for {cand.job.job_fingerprint}: {exc}"
            logger.error(msg)
            summary.source_errors.append(msg)


def run(dry_run: bool = False) -> RunSummary:
    run_started_at = datetime.now(timezone.utc)
    summary = RunSummary()
    career_rules = load_career_rules()
    roles_config = load_roles()
    notion = NotionClient()

    # One bulk read. If it fails we abort rather than risk writing duplicates.
    index = DedupIndex(notion.list_all_pages())
    decisions = DecisionCache(persist=not dry_run)

    jobs = fetch_all(build_sources(), summary)
    candidates = stage0_filter_and_dedupe(jobs, index, decisions, career_rules, roles_config, summary)
    vetted = evaluate(candidates, decisions, career_rules, summary)
    if not dry_run:
        write_to_notion(vetted, notion, summary)

    summary.estimated_cost_usd = estimate_run_cost("classify_job", run_started_at) + estimate_run_cost(
        "analyse_match", run_started_at
    )
    return summary


if __name__ == "__main__":
    from src.telemetry.logging import configure_logging

    configure_logging()
    print(run().as_text())
