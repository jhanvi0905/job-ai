"""Job identity & deduplication (PRD §12). Pure functions, no I/O."""
from __future__ import annotations

import hashlib
import re


def _canonicalize(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip().lower())


def compute_fingerprint(
    source: str,
    external_job_id: str,
    company_name: str,
    title: str,
    location: str | None,
    job_url: str,
) -> str:
    """Preferred identity: source + external_job_id (stable, source-guaranteed
    unique). Falls back to a content hash only when either is missing."""
    if source and external_job_id:
        return f"{source}:{external_job_id}"

    basis = "|".join(
        [_canonicalize(company_name), _canonicalize(title), _canonicalize(location), _canonicalize(job_url)]
    )
    return "fallback:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()


def compute_description_hash(description: str) -> str:
    """Hash of the cleaned job description — drives re-evaluation on change."""
    cleaned = _canonicalize(description)
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
