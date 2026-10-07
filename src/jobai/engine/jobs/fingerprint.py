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


_COMPANY_SUFFIXES = {"inc", "llc", "ltd", "limited", "gmbh", "corp", "corporation", "co", "plc", "ag", "sa"}
_TITLE_NOISE = re.compile(r"\((?:m/[fw]/d|f/m/d|remote|hybrid|100 ?% ?remote|worldwide)\)|\[remote\]", re.I)


def _alnum_words(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).split()


def content_key(company: str | None, title: str | None) -> str:
    """Source-independent identity for 'the same role at the same company'.

    The fingerprint (source:id) can't tell that Himalayas' listing and the
    company's own Greenhouse listing are one job, or that a company re-posted
    an identical req under a new id. company+title can. Deliberately ignores
    location: five identical 'Senior Data Engineer' reqs in five cities are
    one thing to review, not five."""
    company_words = [w for w in _alnum_words(company or "") if w not in _COMPANY_SUFFIXES]
    title_words = _alnum_words(_TITLE_NOISE.sub(" ", title or ""))
    return " ".join(company_words) + "|" + " ".join(title_words)


def compute_description_hash(description: str) -> str:
    """Hash of the cleaned job description — drives re-evaluation on change."""
    cleaned = _canonicalize(description)
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
