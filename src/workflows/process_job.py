"""Phase 1 pipeline: fetch -> normalize -> dedupe -> deterministic filter -> Notion.

No AI calls in this module by design (PRD Phase 1). Stage 1/2/3 (AI triage,
achievement retrieval, deep match) plug in later at the single seam marked
below, once Gate 1 (model verification) has passed — see scripts/verify_models.py.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from src.config import load_career_rules, load_roles, load_sources
from src.integrations.notion import NotionClient
from src.jobs.filters import apply_filters
from src.jobs.normalize import normalize_job
from src.jobs.schemas import NormalizedJob
from src.sources.ashby import AshbySource
from src.sources.base import JobSource
from src.sources.greenhouse import GreenhouseSource
from src.sources.lever import LeverSource
from src.sources.smartrecruiters import SmartRecruitersSource
from src.telemetry.logging import RunSummary

logger = logging.getLogger(__name__)

SOURCE_TYPES: dict[str, type[JobSource]] = {
    "greenhouse": GreenhouseSource,
    "lever": LeverSource,
    "smartrecruiters": SmartRecruitersSource,
    "ashby": AshbySource,
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
    have to re-query the same fingerprint a second time."""
    survivors: list[tuple[NormalizedJob, dict | None]] = []
    for job in jobs:
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

        result = apply_filters(job, career_rules, roles_config)
        if not result.passed:
            summary.stale_or_filtered += 1
            logger.debug("filtered out %s @ %s: %s", job.title, job.company_name, result.reasons)
            continue

        summary.new_candidates += 1
        survivors.append((job, existing))
    return survivors


def _existing_jd_hash(page: dict) -> str | None:
    try:
        rich = page["properties"]["JD Hash"]["rich_text"]
        return rich[0]["text"]["content"] if rich else None
    except (KeyError, IndexError, TypeError):
        return None


def write_to_notion(
    survivors: list[tuple[NormalizedJob, dict | None]], notion: NotionClient, summary: RunSummary
) -> None:
    today = date.today().isoformat()
    for job, existing in survivors:
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
    summary = RunSummary()
    career_rules = load_career_rules()
    roles_config = load_roles()
    notion = NotionClient()

    sources = build_sources()
    jobs = fetch_all(sources, summary)
    survivors = dedupe_and_filter(jobs, notion, career_rules, roles_config, summary)

    # --- Stage 1/2/3 seam -------------------------------------------------
    # Phase 1 (current): write Stage-0 survivors straight to Notion as
    # "Discovered" for manual review — proves acquisition + Notion integration
    # end to end before any AI spend.
    #
    # Phase 2+ (next): replace the line below with
    #   classified = [classify(job) for job in survivors if relevant]
    #   shortlisted = [j for j in classified if j.relevant and not j.hard_blocker]
    #   matches = [analyse_match(job, retrieve_achievements(job)) for job in shortlisted]
    # and write the richer properties (Role Family, Fit Band, evidence, gaps)
    # instead of the bare Stage-0 record. src/ai/{classifier,matcher}.py and
    # src/achievements/* already define the contracts for this.
    write_to_notion(survivors, notion, summary)

    return summary


if __name__ == "__main__":
    from src.telemetry.logging import configure_logging

    configure_logging()
    result = run()
    print(result.as_text())
