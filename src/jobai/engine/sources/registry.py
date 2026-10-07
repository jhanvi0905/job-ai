"""Source registry: maps config entries to ATS adapters and fetches them.

Shared by the single-user pipeline and the multi-tenant catalog ingest, so it
lives in the engine. One source's failure never halts the others.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor

from jobai.core.telemetry.logging import RunSummary
from jobai.engine.jobs.normalize import normalize_job
from jobai.engine.jobs.schemas import NormalizedJob
from jobai.engine.sources.ashby import AshbySource
from jobai.engine.sources.base import JobSource
from jobai.engine.sources.greenhouse import GreenhouseSource
from jobai.engine.sources.himalayas import HimalayasSource
from jobai.engine.sources.lever import LeverSource
from jobai.engine.sources.smartrecruiters import SmartRecruitersSource

logger = logging.getLogger(__name__)

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
SEQUENTIAL_SOURCE_TYPES = {"himalayas"}


def build_sources(companies: Iterable[dict]) -> list[JobSource]:
    """Config entries ({name, source: {type, identifier}}) -> adapters, de-duplicated
    by (type, identifier) so overlapping config files never fetch a board twice."""
    sources: list[JobSource] = []
    seen: set[tuple[str, str]] = set()
    for company in companies:
        src_cfg = company["source"]
        key = (src_cfg["type"], src_cfg["identifier"])
        if key in seen:
            continue
        source_cls = SOURCE_TYPES.get(src_cfg["type"])
        if source_cls is None:
            logger.warning("unknown source type '%s' for %s — skipping", src_cfg["type"], company["name"])
            continue
        seen.add(key)
        sources.append(source_cls(company_name=company["name"], identifier=src_cfg["identifier"]))
    return sources


def _fetch_one(source: JobSource, summary: RunSummary) -> tuple[list[NormalizedJob], int]:
    """Returns (normalized jobs, raw count); counting happens in the caller's thread."""
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
    sequential_classes = tuple(SOURCE_TYPES[t] for t in SEQUENTIAL_SOURCE_TYPES)
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
