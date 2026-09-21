"""Pipeline: fetch -> normalize -> deterministic filter -> dedupe -> cheap AI
triage -> Notion.

Stage 0 (everything through dedupe_and_filter) is zero-AI-call and safe to
run as often as you like. Stage 1 (classify_survivors) is the one AI-calling
step in the automatic batch flow — one cheap classification call per Stage-0
survivor, never the full raw fetch, which is what keeps this affordable
(PRD §15/§19: progressive intelligence, narrow before reasoning). It exists
because Stage 0's keyword-assist alone lets through generic "Software
Engineer" postings that share an AI company's boilerplate vocabulary without
being AI/ML roles — something only role-taxonomy-aware judgment can catch.
Stage 2/3 (achievement retrieval + deep match) stay on-demand only, via
capabilities.analyse_job() — see that module for why full evidence/gap
writing per-job stays a deliberate action, not automatic batch behavior.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from src.ai.classifier import classify_job
from src.ai.role_labels import ROLE_FAMILY_LABELS
from src.config import load_career_rules, load_roles, load_sources
from src.integrations.notion import NotionClient
from src.jobs.filters import apply_filters
from src.jobs.normalize import normalize_job
from src.jobs.schemas import JobClassification, NormalizedJob
from src.sources.ashby import AshbySource
from src.sources.base import JobSource
from src.sources.greenhouse import GreenhouseSource
from src.sources.himalayas import HimalayasSource
from src.sources.lever import LeverSource
from src.sources.smartrecruiters import SmartRecruitersSource
from src.telemetry.logging import RunSummary
from src.telemetry.usage import estimate_run_cost

logger = logging.getLogger(__name__)

SOURCE_TYPES: dict[str, type[JobSource]] = {
    "greenhouse": GreenhouseSource,
    "lever": LeverSource,
    "smartrecruiters": SmartRecruitersSource,
    "ashby": AshbySource,
    "himalayas": HimalayasSource,
}


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


def fetch_all(sources: list[JobSource], summary: RunSummary) -> list[NormalizedJob]:
    """One source's failure must not halt the others (PRD §33)."""
    normalized: list[NormalizedJob] = []
    for source in sources:
        try:
            raw_jobs = source.fetch_jobs()
        except Exception as exc:  # noqa: BLE001
            msg = f"{source.__class__.__name__}({source.identifier}): {exc}"
            logger.error("source fetch failed: %s", msg)
            summary.source_errors.append(msg)
            continue
        summary.fetched += len(raw_jobs)
        for raw in raw_jobs:
            try:
                normalized.append(normalize_job(raw))
            except Exception:  # noqa: BLE001
                logger.warning("normalize failed for %s/%s", raw.source, raw.external_job_id, exc_info=True)
    return normalized


def dedupe_and_filter(
    jobs: list[NormalizedJob],
    notion: NotionClient,
    career_rules: dict,
    roles_config: dict,
    summary: RunSummary,
) -> list[tuple[NormalizedJob, dict | None]]:
    """Returns (job, existing_notion_page_or_None) so write_to_notion doesn't
    have to re-query the same fingerprint a second time.

    Order matters here: apply_filters() first (free, local, instant), THEN
    the Notion dedup lookup (a network round-trip) — only for jobs that
    already survived filtering. Doing it the other way around means one
    Notion API call per RAW fetched job (thousands) instead of per Stage-0
    survivor (tens) — this was a real bug in an earlier version that made a
    single run take 20+ minutes on network I/O alone. Progressive
    intelligence (PRD §2.3) applies to every expensive operation, not just AI
    calls — Notion API round-trips are exactly this kind of expensive step.

    Also tracks fingerprints already handled WITHIN this run (not just
    Notion's state as of the start of the run). Aggregator sources like
    Himalayas can return the same underlying job from more than one
    configured query (e.g. a globally-open role matches both an India-
    specific and a worldwide search) — without this, each repeat looked
    "new" (Notion didn't have it yet either, since nothing had been written
    yet) and got written as a separate duplicate Notion page, and
    classified by AI more than once. Real bug, found by inspecting actual
    Notion output, not by inspection of the code alone.
    """
    survivors: list[tuple[NormalizedJob, dict | None]] = []
    seen_fingerprints: set[str] = set()
    for job in jobs:
        if job.job_fingerprint in seen_fingerprints:
            summary.duplicates += 1
            continue

        result = apply_filters(job, career_rules, roles_config)
        if not result.passed:
            summary.stale_or_filtered += 1
            logger.debug("filtered out %s @ %s: %s", job.title, job.company_name, result.reasons)
            continue

        seen_fingerprints.add(job.job_fingerprint)
        try:
            existing = notion.find_by_fingerprint(job.job_fingerprint)
        except Exception as exc:  # noqa: BLE001 — one job's Notion hiccup must not kill the batch
            msg = f"dedupe lookup failed for {job.source}:{job.external_job_id}: {exc}"
            logger.error(msg)
            summary.source_errors.append(msg)
            continue

        if existing is not None:
            existing_hash = _existing_jd_hash(existing)
            if existing_hash == job.description_hash:
                summary.duplicates += 1
                continue
            # Fingerprint matches but description changed -> re-evaluate (PRD §12).

        summary.new_candidates += 1
        survivors.append((job, existing))
    return survivors


def _existing_jd_hash(page: dict) -> str | None:
    try:
        rich = page["properties"]["JD Hash"]["rich_text"]
        return rich[0]["text"]["content"] if rich else None
    except (KeyError, IndexError, TypeError):
        return None


def classify_survivors(
    survivors: list[tuple[NormalizedJob, dict | None]], summary: RunSummary
) -> list[tuple[NormalizedJob, dict | None, JobClassification]]:
    """Stage 1: one cheap AI call per Stage-0 survivor — judges actual role
    fit (including seniority/years) against the role taxonomy, not just
    keyword presence. A classification failure fails OPEN (job still passes
    through, unclassified) rather than silently dropping a job a human never
    gets to see because of an API hiccup — infra failures aren't evidence of
    irrelevance."""
    results: list[tuple[NormalizedJob, dict | None, JobClassification]] = []
    for job, existing in survivors:
        try:
            classification = classify_job(job)
            summary.classified += 1
        except Exception as exc:  # noqa: BLE001
            msg = f"classification failed for {job.source}:{job.external_job_id}: {exc}"
            logger.error(msg)
            summary.ai_errors.append(msg)
            results.append((job, existing, None))
            continue

        if classification.hard_blocker or not classification.relevant:
            logger.debug(
                "excluded by Stage 1: %s @ %s (relevant=%s, hard_blocker=%s: %s)",
                job.title,
                job.company_name,
                classification.relevant,
                classification.hard_blocker,
                classification.hard_blocker_reason,
            )
            continue

        results.append((job, existing, classification))
    return results


def write_to_notion(
    survivors: list[tuple[NormalizedJob, dict | None, JobClassification | None]],
    notion: NotionClient,
    summary: RunSummary,
) -> None:
    today = date.today().isoformat()
    for job, existing, classification in survivors:
        properties = {
            "Opportunity": f"{job.title} — {job.company_name}",
            "Company": job.company_name,
            "Role": job.title,
            "Location": job.location,
            "Job URL": job.job_url,
            "Status": "Discovered",
            "Source": "Automation",
            "Source Channel": "Company Careers",
            "Work Mode": job.workplace_type,
            "External Key": f"{job.source}:{job.external_job_id}",
            "Job Fingerprint": job.job_fingerprint,
            "JD Hash": job.description_hash,
            "Found Date": today,
            "Last Checked": today,
            "Date Posted": job.posted_at.date().isoformat() if job.posted_at else None,
        }
        if classification is not None:
            properties["Role Family"] = ROLE_FAMILY_LABELS.get(classification.role_family)
            properties["Seniority"] = classification.seniority
        try:
            if existing is not None:
                notion.update_job_page(existing["id"], properties)
            else:
                notion.create_job_page(properties)
            summary.written_to_notion += 1
        except Exception as exc:  # noqa: BLE001 — one job's write failing must not kill the batch
            msg = f"Notion write failed for {job.source}:{job.external_job_id}: {exc}"
            logger.error(msg)
            summary.source_errors.append(msg)


def run() -> RunSummary:
    run_started_at = datetime.now(timezone.utc)
    summary = RunSummary()
    career_rules = load_career_rules()
    roles_config = load_roles()
    notion = NotionClient()

    sources = build_sources()
    jobs = fetch_all(sources, summary)
    stage0_survivors = dedupe_and_filter(jobs, notion, career_rules, roles_config, summary)
    stage1_survivors = classify_survivors(stage0_survivors, summary)

    # Stage 2/3 (achievement retrieval + deep match) deliberately stay
    # on-demand only — capabilities.analyse_job() — not automatic here. See
    # module docstring for why.
    write_to_notion(stage1_survivors, notion, summary)

    summary.estimated_cost_usd = estimate_run_cost(workflow="classify_job", since=run_started_at)
    return summary


if __name__ == "__main__":
    from src.telemetry.logging import configure_logging

    configure_logging()
    result = run()
    print(result.as_text())
