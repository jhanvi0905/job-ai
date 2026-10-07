"""Stage 0 — deterministic filtering. Zero model calls (PRD §14)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC

from jobai.engine.jobs.experience import extract_required_years
from jobai.engine.jobs.normalize import utcnow
from jobai.engine.jobs.role_taxonomy import match_title
from jobai.engine.jobs.schemas import NormalizedJob


@dataclass
class FilterResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)
    keyword_score: int = 0
    min_years_required: int | None = None
    years_evidence: str = ""
    # One closed-vocabulary code per reason, same order. codes[0] is the PRIMARY
    # reason (the first rule that fired) — the one the funnel counts.
    codes: list[str] = field(default_factory=list)
    # Role-taxonomy-v2 families the title matched (product path only; empty on the legacy path).
    families: list[str] = field(default_factory=list)


# Message fragment -> reason code. Kept next to the messages so a new rule and
# its code are edited together; tests assert no real message falls through to
# "stage0_other" (which would hide a rule inside an 'other' bucket).
_REASON_CODES = [
    ("stale:", "stale"),
    ("not in allowed list", "workplace_type"),
    ("location unknown", "location_unknown"),
    ("structured location_country", "location_restricted"),
    ("role not located in", "location_restricted"),
    ("remote but restricted", "location_restricted"),
    ("employment_type", "employment_type"),
    ("seniority exclusion", "junior_title"),
    ("too senior", "too_senior_title"),
    ("yrs (you have", "years_too_high"),
    ("junior-level ask", "junior_ask"),
    ("hard exclusion", "hard_exclusion"),
    ("no title-family match", "no_signal"),
    ("non-engineering data/analyst", "analyst_title"),
    ("no AI/ML/data signal", "generic_title"),
]


def code_for_reason(message: str) -> str:
    for fragment, code in _REASON_CODES:
        if fragment in message:
            return code
    return "stage0_other"


def _has_any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)


def _title_matches_any_family(title: str, roles_config: dict) -> bool:
    title_lower = title.lower()
    for family in roles_config["role_families"].values():
        for alias in family["title_aliases"]:
            if alias.lower() in title_lower:
                return True
    return False


def _location_eligible(job: NormalizedJob, loc_cfg: dict) -> tuple[bool, str | None]:
    """Eligibility, not geography: can a candidate based in candidate_country
    actually work this job. Returns (eligible, reason_if_not)."""
    candidate_country = loc_cfg["candidate_country"].lower()
    location_text = (job.location or "").lower()

    # Structured country (Ashby) beats any text guess when present — for
    # EVERY workplace type, not just on-site/hybrid. A "Remote" job whose ATS
    # record still carries a specific addressCountry is real signal ("US -
    # Remote" really does mean US-eligible-only on Ashby), unless the text
    # also signals global/candidate_country scope (an HQ default address
    # doesn't always mean the role itself is geo-restricted).
    if job.location_country:
        country_lower = job.location_country.lower()
        if candidate_country in country_lower or country_lower in candidate_country:
            return True, None
        if job.workplace_type == "Remote":
            haystack = f"{location_text} {job.description.lower()[:500]}"
            if candidate_country in haystack or any(sig in haystack for sig in loc_cfg["eligible_signals"]):
                return True, None
        return False, f"structured location_country='{job.location_country}', not {loc_cfg['candidate_country']}"

    if job.workplace_type in ("On-site", "Hybrid"):
        # Only eligible if physically located in the candidate's country.
        # `country_aliases` (product path: cities/provinces such as "Toronto, ON")
        # is absent from the legacy config, so legacy behaviour is unchanged.
        if candidate_country in location_text or _has_any(loc_cfg.get("country_aliases", []), location_text):
            return True, None
        return False, f"{job.workplace_type} role not located in {loc_cfg['candidate_country']}"

    if job.workplace_type == "Remote":
        haystack = f"{location_text} {job.description.lower()[:500]}"  # title/location context is usually enough; cap cost
        has_global_scope = candidate_country in haystack or any(
            sig in haystack for sig in loc_cfg["eligible_signals"]
        )

        restrictive_hit = next(
            (sig for sig in loc_cfg["restrictive_signals"] if sig in haystack), None
        )
        # "Remote - United States" style location strings rarely use prose
        # restriction phrases — catch the named region directly.
        named_region_hit = next(
            (region for region in loc_cfg.get("location_named_regions", []) if region in location_text),
            None,
        )

        if (restrictive_hit or named_region_hit) and not has_global_scope:
            reason = restrictive_hit or f"location names '{named_region_hit}'"
            return False, f"remote but restricted ('{reason}'), no mention of {loc_cfg['candidate_country']} or global scope"
        return True, None

    return True, None  # Unknown workplace_type handled by the caller


def _keyword_score(job: NormalizedJob, career_rules: dict) -> tuple[list[str], int]:
    weights: dict[str, int] = career_rules["keyword_weights"]
    matched: list[str] = []
    score = 0
    haystack = f"{job.title} {job.description}".lower()
    for kw, weight in weights.items():
        if kw.lower() in haystack:
            matched.append(kw)
            score += weight
    return matched, score


def apply_filters(job: NormalizedJob, career_rules: dict, roles_config: dict) -> FilterResult:
    reasons: list[str] = []

    # --- Recency ---
    max_age_days = career_rules["recency"]["max_age_days"]
    if job.posted_at is not None:
        posted = job.posted_at
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=UTC)
        age_days = (utcnow() - posted).days
        if age_days > max_age_days:
            reasons.append(f"stale: posted {age_days}d ago (max {max_age_days}d)")

    # --- Location eligibility (works FROM candidate_country, any company) ---
    loc_cfg = career_rules["location"]
    if job.workplace_type == "Unknown":
        if not loc_cfg.get("unknown_location_passes_through", True):
            reasons.append("location unknown and pass-through disabled")
    elif job.workplace_type not in loc_cfg["allowed_workplace_types"]:
        reasons.append(f"workplace_type '{job.workplace_type}' not in allowed list")
    else:
        eligible, reason = _location_eligible(job, loc_cfg)
        if not eligible:
            reasons.append(reason)

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

    # --- Too-senior titles (Director/Staff/Principal/...): whole words, title only ---
    # `not_too_senior` (product path) lists ordinary titles that contain such a word ("Staff Accountant").
    ordinary_title = _has_any(career_rules["seniority"].get("not_too_senior", []), title_lower)
    for kw in career_rules["seniority"].get("too_senior_title_keywords", []):
        if not ordinary_title and re.search(rf"\b{re.escape(kw.lower())}\b", title_lower):
            reasons.append(f"too senior for {career_rules['experience']['total_years']}y experience: '{kw}' in title")
            break

    # --- Years-of-experience gate (regex over the JD, zero tokens) ---
    exp_cfg = career_rules["experience"]
    years_req = extract_required_years(job.description)
    min_years = years_req.min_years if years_req else None
    if years_req:
        if years_req.min_years > exp_cfg["max_required_years"]:
            reasons.append(
                f"asks {years_req.min_years}+ yrs (you have ~{exp_cfg['total_years']}): \"{years_req.evidence[:70]}\""
            )
        elif years_req.max_years is not None and years_req.max_years <= exp_cfg["junior_cap_years"]:
            reasons.append(f"junior-level ask ({years_req.min_years}-{years_req.max_years} yrs)")

    # --- Hard exclusions: title + description ---
    for kw in career_rules["hard_exclusions"]["title_keywords"]:
        if kw.lower() in title_lower:
            reasons.append(f"hard exclusion keyword in title: '{kw}'")
    desc_lower = job.description.lower()
    for kw in career_rules["hard_exclusions"]["description_keywords"]:
        if kw.lower() in desc_lower:
            reasons.append(f"hard exclusion keyword in description: '{kw}'")

    # --- Product path (role taxonomy v2): the title must belong to one of the
    # user's families, judged by that family's positive and negative signals.
    # Replaces the AI/ML-specific title checks below; keyword weights still rank.
    family_cfg = career_rules.get("family_filter")
    if family_cfg is not None:
        families, reason = match_title(job.title, family_cfg)
        if reason:
            reasons.append(reason)
        matched, score = _keyword_score(job, career_rules)
        return FilterResult(
            passed=len(reasons) == 0, reasons=reasons, matched_keywords=matched, keyword_score=score,
            min_years_required=min_years, years_evidence=years_req.evidence if years_req else "",
            codes=[code_for_reason(r) for r in reasons], families=families,
        )

    # --- Title-family matching (assist, not a hard requirement on its own —
    # but a job matching NEITHER a title alias NOR any keyword is almost
    # certainly noise, so it's excluded here to protect Stage 1 token budget) ---
    title_family_match = _title_matches_any_family(job.title, roles_config)

    # --- Keyword weighting (assist / ranking signal only) ---
    matched, score = _keyword_score(job, career_rules)

    if not title_family_match and score == 0:
        reasons.append("no title-family match and no keyword signal")

    # --- Title must carry an AI/ML/data signal (or a role-family alias) ---
    # Generic "Software Engineer - Backend/Infra/Search" rows only survived
    # before because AI companies repeat AI vocabulary in every posting's
    # boilerplate; the title is the reliable signal.
    signals = career_rules.get("title_signals", {})
    if signals:
        if _has_any(signals.get("reject_if_any", []), title_lower):
            reasons.append("title is a non-engineering data/analyst role")
        elif not title_family_match and not _has_any(signals.get("require_any", []), title_lower):
            reasons.append("title has no AI/ML/data signal (generic engineering role)")

    return FilterResult(
        passed=len(reasons) == 0,
        reasons=reasons,
        matched_keywords=matched,
        keyword_score=score,
        min_years_required=min_years,
        years_evidence=years_req.evidence if years_req else "",
        codes=[code_for_reason(r) for r in reasons],
    )
