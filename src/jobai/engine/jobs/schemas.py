"""Typed contracts for the pipeline. Pydantic validates every boundary crossing."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RawJob(BaseModel):
    """Source-specific representation, unvalidated beyond basic typing."""

    source: str
    source_company_identifier: str
    external_job_id: str
    title: str
    company_name: str
    location: str | None = None
    description_html: str | None = None
    absolute_url: str | None = None
    updated_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class NormalizedJob(BaseModel):
    """Stable cross-source schema. Fields unavailable from a source stay null —
    never fabricated."""

    external_job_id: str
    source: str
    source_company_identifier: str
    company_name: str
    title: str
    location: str | None = None
    workplace_type: Literal["Remote", "Hybrid", "On-site", "Unknown"] | None = "Unknown"
    # Structured country, when the source provides one (e.g. Ashby's
    # address.postalAddress.addressCountry). None for sources that only give
    # free text (Greenhouse/Lever/SmartRecruiters) — filters.py falls back to
    # text signals in that case. Never guessed/fabricated.
    location_country: str | None = None
    employment_type: str | None = None
    description: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    posted_at: datetime | None = None
    updated_at: datetime | None = None
    job_url: str
    application_url: str | None = None
    raw_source_payload: dict[str, Any] = Field(default_factory=dict)

    # Identity, computed by fingerprint.py after construction.
    job_fingerprint: str | None = None
    description_hash: str | None = None


class JobClassification(BaseModel):
    """Stage 1 cheap-AI triage result. Schema-validated LLM output.

    `relevant` is NOT taken on trust from the model: the classifier derives it
    from role_type + fit + hard_blocker against config/career_rules.yaml
    (ai_gates), so the model can't wave through a marketing role by calling it
    "relevant"."""

    role_family: str | None = None
    # Normalised vocabulary (see prompts/classify_job_v2.txt), not free text.
    seniority: str | None = None
    role_type: str | None = None
    fit: Literal["strong", "plausible", "weak", "no"] | None = None
    min_years_required: int | None = None
    why: str | None = None
    relevant: bool
    hard_blocker: bool = False
    hard_blocker_reason: str | None = None
    key_requirements: list[str] = Field(default_factory=list)


class MatchedAchievement(BaseModel):
    id: str
    strength: Literal["strong", "plausible", "weak"]
    supports: list[str] = Field(default_factory=list)


class JobMatch(BaseModel):
    """Stage 3 deep evidence-based analysis. Schema-validated LLM output."""

    fit_band: Literal["strong", "plausible", "weak", "blocked"]
    priority: Literal["P1", "P2", "P3"]
    matched_achievements: list[MatchedAchievement] = Field(default_factory=list)
    strong_evidence: list[str] = Field(default_factory=list)
    partial_evidence: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    reason: str
    recommended_action: Literal["review", "watch", "reject"] = "review"
    # Set by the caller (capabilities.analyse_job) after the LLM response is
    # validated — not part of the LLM's own output.
    run_id: str | None = None


# Re-exported for older imports; the record is telemetry and lives in core.
from jobai.core.telemetry.records import AIUsageRecord  # noqa: E402,F401
