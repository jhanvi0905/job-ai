"""Re-fetches one job's full description from its origin ATS.

Notion intentionally stores only a JD Hash, not the full description (PRD
§5 rules out a second duplicate-storage system, and job descriptions can run
well past Notion's rich_text limits). Since job postings stay live for the
lifetime a review queue cares about, re-fetching from source at analyse_job()
time is simpler and cheaper than maintaining a local JD cache.
"""
from __future__ import annotations

from src.config import load_sources
from src.jobs.normalize import normalize_job
from src.jobs.schemas import NormalizedJob
from src.workflows.process_job import SOURCE_TYPES


class JobNotFoundError(Exception):
    pass


def refetch_job(company_name: str, source_type: str, external_job_id: str) -> NormalizedJob:
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
