"""Typed contracts for the pipeline. Pydantic validates every boundary crossing."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class RawJob(BaseModel):
    """Source-specific representation, unvalidated beyond basic typing."""

    source: str
    source_company_identifier: str
    external_job_id: str
    title: str
    company_name: str
    location: Optional[str] = None
    description_html: Optional[str] = None
    absolute_url: Optional[str] = None
    updated_at: Optional[str] = None
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
    location: Optional[str] = None
    workplace_type: Optional[Literal["Remote", "Hybrid", "On-site", "Unknown"]] = "Unknown"
    # Structured country, when the source provides one (e.g. Ashby's
    # address.postalAddress.addressCountry). None for sources that only give
    # free text (Greenhouse/Lever/SmartRecruiters) — filters.py falls back to
    # text signals in that case. Never guessed/fabricated.
    location_country: Optional[str] = None
    employment_type: Optional[str] = None
    description: str = ""
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = None
    posted_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    job_url: str
    application_url: Optional[str] = None
    raw_source_payload: dict[str, Any] = Field(default_factory=dict)

    # Identity, computed by fingerprint.py after construction.
    job_fingerprint: Optional[str] = None
    description_hash: Optional[str] = None


class JobClassification(BaseModel):
    """Stage 1 cheap-AI triage result. Schema-validated LLM output.

    `relevant` is NOT taken on trust from the model: the classifier derives it
    from role_type + fit + hard_blocker against config/career_rules.yaml
    (ai_gates), so the model can't wave through a marketing role by calling it
    "relevant"."""

    role_family: Optional[str] = None
    # Normalised vocabulary (see prompts/classify_job_v2.txt), not free text.
    seniority: Optional[str] = None
    role_type: Optional[str] = None
    fit: Optional[Literal["strong", "plausible", "weak", "no"]] = None
    min_years_required: Optional[int] = None
    why: Optional[str] = None
    relevant: bool
    hard_blocker: bool = False
    hard_blocker_reason: Optional[str] = None
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


class AIUsageRecord(BaseModel):
    """One row per model call — never rely on provider dashboards alone."""

    timestamp: datetime
    workflow: str
    job_id: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    latency_ms: int
    cache_hit: bool = False
    success: bool = True
    error: Optional[str] = None
