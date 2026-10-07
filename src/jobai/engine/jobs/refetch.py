"""Re-fetches one job's full description from its origin ATS.

Notion intentionally stores only a JD Hash, not the full description (PRD
§5 rules out a second duplicate-storage system, and job descriptions can run
well past Notion's rich_text limits). Since job postings stay live for the
lifetime a review queue cares about, re-fetching from source at analyse_job()
time is simpler and cheaper than maintaining a local JD cache.
"""
from __future__ import annotations

from jobai.core.config import load_sources
from jobai.engine.jobs.normalize import normalize_job
from jobai.engine.jobs.schemas import NormalizedJob
from jobai.engine.sources.registry import SOURCE_TYPES

# Source types where one config entry = one company (Greenhouse/Lever/Ashby/
# SmartRecruiters) — refetch by looking up that exact company's board.
# Aggregator source types (Himalayas) span many companies per config entry,
# so a job's stored company_name won't match any sources.yaml entry name;
# refetch instead has to search across every configured query of that type.
_AGGREGATOR_SOURCE_TYPES = {"himalayas"}


class JobNotFoundError(Exception):
    pass


def refetch_job(company_name: str, source_type: str, external_job_id: str) -> NormalizedJob:
    if source_type in _AGGREGATOR_SOURCE_TYPES:
        return _refetch_from_aggregator(source_type, external_job_id)
    return _refetch_from_company_board(company_name, source_type, external_job_id)


def _refetch_from_company_board(company_name: str, source_type: str, external_job_id: str) -> NormalizedJob:
    company_cfg = next(
        (
            c
            for c in load_sources()
            if c["name"] == company_name and c["source"]["type"] == source_type
        ),
        None,
    )
    if company_cfg is None:
        raise JobNotFoundError(
            f"'{company_name}' ({source_type}) is not in config/sources.yaml — "
            "can't re-fetch its postings."
        )

    source_cls = SOURCE_TYPES[source_type]
    source = source_cls(company_name=company_name, identifier=company_cfg["source"]["identifier"])
    for raw in source.fetch_jobs():
        if raw.external_job_id == external_job_id:
            return normalize_job(raw)

    raise JobNotFoundError(
        f"{company_name}/{external_job_id} was found in Notion but is no longer "
        "posted on the source board (likely closed) — nothing to re-analyse."
    )


def _refetch_from_aggregator(source_type: str, external_job_id: str) -> NormalizedJob:
    """A Himalayas-sourced job's stored company (e.g. 'mercor') isn't itself a
    sources.yaml entry — the config entries are search queries, not
    companies. Re-run every configured query of this source type and look
    for the matching job. Cheap: a handful of requests, not thousands."""
    source_cls = SOURCE_TYPES[source_type]
    queries = [c for c in load_sources() if c["source"]["type"] == source_type]

    for company in queries:
        source = source_cls(company_name=company["name"], identifier=company["source"]["identifier"])
        for raw in source.fetch_jobs():
            if raw.external_job_id == external_job_id:
                return normalize_job(raw)

    raise JobNotFoundError(
        f"{source_type}/{external_job_id} was found in Notion but no longer appears in any "
        f"configured {source_type} query — likely closed or fell off the result window."
    )
