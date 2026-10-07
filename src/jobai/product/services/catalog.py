"""Shared job catalog: fetched once for everyone, never per user.

One failing source never fails the run (fetch_all already isolates sources);
jobs vanish from the catalog only after going unseen for STALE_AFTER_DAYS, so a
temporary source outage doesn't wipe jobs users are looking at.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from jobai.core.config import load_sources, load_yaml
from jobai.core.telemetry.logging import RunSummary
from jobai.engine.jobs.fingerprint import content_key
from jobai.engine.jobs.schemas import NormalizedJob
from jobai.engine.sources.base import JobSource
from jobai.engine.sources.registry import build_sources, fetch_all
from jobai.product.db.models import Job

logger = logging.getLogger(__name__)

STALE_AFTER_DAYS = 14


@dataclass
class IngestSummary:
    fetched: int = 0
    inserted: int = 0
    updated: int = 0  # description changed
    unchanged: int = 0
    deactivated: int = 0
    reactivated: int = 0
    skipped_invalid: int = 0
    source_errors: list[str] = field(default_factory=list)


def _apply(row: Job, job: NormalizedJob) -> None:
    row.content_key = content_key(job.company_name, job.title)
    row.source, row.external_id = job.source, job.external_job_id
    row.company, row.title = job.company_name, job.title
    row.location, row.workplace_type = job.location, job.workplace_type
    row.apply_url = job.application_url or job.job_url
    row.description, row.description_hash = job.description, job.description_hash
    row.posted_at = job.posted_at
    row.normalized = job.model_dump(mode="json", exclude={"raw_source_payload"})  # payload is bulky and unused downstream


def catalog_sources() -> list[JobSource]:
    """Boards from config/sources_catalog.yaml (broad Canadian employers, each
    verified live), plus the legacy AI/ML boards when `include_legacy_sources`."""
    cfg = load_yaml("sources_catalog.yaml")
    companies = list(cfg.get("companies", []))
    if cfg.get("include_legacy_sources", False):
        companies += load_sources()
    return build_sources(companies)


def ingest_catalog(
    session: Session, sources: list[JobSource] | None = None, now: datetime | None = None
) -> IngestSummary:
    """Upsert normalized jobs by fingerprint, refresh last_seen_at, and
    deactivate jobs unseen for STALE_AFTER_DAYS. Idempotent."""
    now = now or datetime.now(UTC)
    summary = IngestSummary()
    run = RunSummary()
    jobs = fetch_all(sources if sources is not None else catalog_sources(), run)
    summary.fetched = run.fetched
    summary.source_errors = list(run.source_errors)

    batch: dict[str, NormalizedJob] = {}
    for job in jobs:
        if not job.job_fingerprint or not job.description_hash:
            summary.skipped_invalid += 1
            continue
        batch[job.job_fingerprint] = job  # same posting from two queries: last wins

    existing = {}
    if batch:
        existing = {r.fingerprint: r for r in session.scalars(select(Job).where(Job.fingerprint.in_(list(batch))))}

    for fp, job in batch.items():
        row = existing.get(fp)
        if row is None:
            row = Job(fingerprint=fp, first_seen_at=now, last_seen_at=now, active=True)
            _apply(row, job)
            session.add(row)
            summary.inserted += 1
            continue
        if not row.active:
            summary.reactivated += 1
        row.active = True
        row.last_seen_at = now
        if row.description_hash != job.description_hash:
            _apply(row, job)
            summary.updated += 1
        else:
            summary.unchanged += 1

    # Time-based, so an outage shorter than STALE_AFTER_DAYS deactivates nothing.
    cutoff = now - timedelta(days=STALE_AFTER_DAYS)
    result = session.execute(
        update(Job).where(Job.active.is_(True), Job.last_seen_at < cutoff).values(active=False)
    )
    summary.deactivated = result.rowcount or 0
    session.flush()
    logger.info("catalog ingest: %s", summary)
    return summary
