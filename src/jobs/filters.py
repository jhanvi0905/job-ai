"""Stage 0 — deterministic filtering. Zero model calls (PRD §14)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.jobs.normalize import utcnow
from src.jobs.schemas import NormalizedJob


@dataclass
class FilterResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    keyword_score: int = 0


def _title_matches_any_family(title: str, roles_config: dict) -> bool:
    title_lower = title.lower()
    for family in roles_config["role_families"].values():
        for alias in family["title_aliases"]:
            if alias.lower() in title_lower:
                return True
    return False


def apply_filters(job: NormalizedJob, career_rules: dict, roles_config: dict) -> FilterResult:
    reasons: list[str] = []

    # --- Recency ---
    max_age_days = career_rules["recency"]["max_age_days"]
    if job.posted_at is not None:
        posted = job.posted_at
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        age_days = (utcnow() - posted).days
        if age_days > max_age_days:
            reasons.append(f"stale: posted {age_days}d ago (max {max_age_days}d)")

    # --- Location / workplace type ---
    loc_cfg = career_rules["location"]
    if job.workplace_type == "Unknown":
        if not loc_cfg.get("unknown_location_passes_through", True):
            reasons.append("location unknown and pass-through disabled")
    elif job.workplace_type not in loc_cfg["allowed_workplace_types"]:
        reasons.append(f"workplace_type '{job.workplace_type}' not in allowed list")

    # --- Employment type hard exclusion ---
    excluded_types = {t.lower() for t in career_rules["employment_type"]["excluded"]}
    if job.employment_type and job.employment_type.lower() in excluded_types:
        reasons.append(f"employment_type '{job.employment_type}' excluded")

    # --- Seniority hard exclusions (title only — cheap, deterministic) ---
    title_lower = job.title.lower()
    for kw in career_rules["seniority"]["hard_exclude_keywords"]:
        if kw.lower() in title_lower:
            reasons.append(f"seniority exclusion keyword in title: '{kw}'")
            break

    # --- Hard exclusions: title + description ---
    for kw in career_rules["hard_exclusions"]["title_keywords"]:
        if kw.lower() in title_lower:
            reasons.append(f"hard exclusion keyword in title: '{kw}'")
    desc_lower = job.description.lower()
    for kw in career_rules["hard_exclusions"]["description_keywords"]:
        if kw.lower() in desc_lower:
            reasons.append(f"hard exclusion keyword in description: '{kw}'")

    # --- Title-family matching (assist, not a hard requirement on its own —
    # but a job matching NEITHER a title alias NOR any keyword is almost
    # certainly noise, so it's excluded here to protect Stage 1 token budget) ---
    title_family_match = _title_matches_any_family(job.title, roles_config)

    # --- Keyword weighting (assist / ranking signal only) ---
    weights: dict[str, int] = career_rules["keyword_weights"]
    matched: list[str] = []
    score = 0
    haystack = f"{job.title} {job.description}".lower()
    for kw, weight in weights.items():
        if kw.lower() in haystack:
            matched.append(kw)
            score += weight

    if not title_family_match and score == 0:
        reasons.append("no title-family match and no keyword signal")

    return FilterResult(
        passed=len(reasons) == 0,
        reasons=reasons,
        matched_keywords=matched,
        keyword_score=score,
    )
