"""RawJob -> NormalizedJob. Deterministic, no AI, no fabricated fields."""
from __future__ import annotations

import re
from datetime import UTC, datetime

from jobai.engine.jobs.fingerprint import compute_description_hash, compute_fingerprint
from jobai.engine.jobs.schemas import NormalizedJob, RawJob

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(html: str | None) -> str:
    if not html:
        return ""
    text = _TAG_RE.sub(" ", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return _WS_RE.sub(" ", text).strip()


_ASHBY_WORKPLACE_MAP = {"Remote": "Remote", "Hybrid": "Hybrid", "OnSite": "On-site"}


def infer_workplace_type(location: str | None, structured_workplace_type: str | None = None) -> str:
    # Prefer a source's own structured field (e.g. Ashby's workplaceType) —
    # it's the ATS's own classification, not a guess from free text.
    if structured_workplace_type:
        mapped = _ASHBY_WORKPLACE_MAP.get(structured_workplace_type)
        if mapped:
            return mapped

    if not location:
        return "Unknown"
    loc = location.lower()
    if "remote" in loc:
        return "Remote"
    if "hybrid" in loc:
        return "Hybrid"
    # A concrete city/region with no remote/hybrid marker reads as on-site —
    # but we never claim confidence we don't have.
    if any(ch.isalpha() for ch in loc):
        return "On-site"
    return "Unknown"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_job(raw: RawJob) -> NormalizedJob:
    description = strip_html(raw.description_html)
    job_url = raw.absolute_url or ""

    job = NormalizedJob(
        external_job_id=raw.external_job_id,
        source=raw.source,
        source_company_identifier=raw.source_company_identifier,
        company_name=raw.company_name,
        title=raw.title.strip(),
        location=raw.location,
        workplace_type=infer_workplace_type(raw.location, raw.metadata.get("workplace_type")),
        location_country=raw.metadata.get("location_country"),
        employment_type=raw.metadata.get("commitment"),
        description=description,
        posted_at=_parse_datetime(raw.updated_at),
        updated_at=_parse_datetime(raw.updated_at),
        job_url=job_url,
        application_url=job_url,
        raw_source_payload=raw.raw_payload,
    )

    job.job_fingerprint = compute_fingerprint(
        source=job.source,
        external_job_id=job.external_job_id,
        company_name=job.company_name,
        title=job.title,
        location=job.location,
        job_url=job.job_url,
    )
    job.description_hash = compute_description_hash(job.description)
    return job


def utcnow() -> datetime:
    return datetime.now(UTC)
