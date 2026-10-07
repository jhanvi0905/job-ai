"""Per-user search preferences -> the engine's config shapes.

The engine reads `career_rules`, a candidate `profile` and an achievement
`index` as plain dicts. This module builds all three from a user's DB rows so
the matching code never learns about tenants: it just receives different dicts.

Role families (docs/COVERAGE.md): a user's families come from their prefs, else
are inferred from their achievements' tags; with neither, the user has not
chosen yet (`needs_choice`) and the engine keeps the pre-taxonomy AI/ML/data
behaviour until the frontend asks them. Once families are known, Stage 0, the
triage prompt (classify_job_v3) and the relevance gate all use taxonomy v2.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobai.core.config import load_career_rules, load_models, load_roles, load_yaml
from jobai.engine.jobs.decisions import PROMPTS_DIR
from jobai.engine.jobs.role_taxonomy import (
    adjacent_of,
    family_filter,
    infer_families,
    load_taxonomy,
    normalize_families,
    normalize_family,
    not_too_senior_phrases,
    taxonomy_digest,
    vocab_weights,
)
from jobai.product.db.models import Achievement, SearchPrefs

WorkplaceType = Literal["Remote", "Hybrid", "On-site"]

# Signals in the shipped config that are specific to one candidate's country;
# they are replaced by the user's own countries below.
_COUNTRY_SPECIFIC_SIGNALS = {"india", "apac"}
_APAC = {"india", "singapore", "australia", "japan", "new zealand"}
# Title exclusions that are about eligibility, not job function: they survive the
# switch to taxonomy v2 (the function-based ones — "sales", "recruiter", ... — are
# exactly what other users now want, so the families' own signals replace them).
_ELIGIBILITY_TITLE_EXCLUSIONS = {"security clearance required", "ts/sci", "citizenship required"}
# Seniority words that mean "too junior" for most users; open_to_junior lifts them.
_JUNIOR_TITLE_WORDS = {"junior", "entry level", "entry-level", "new grad", "apprentice"}
_LIST_FIELDS = ("role_families", "skills", "system_patterns", "seniority_signals", "business_signals", "leadership_signals")


def _default_excluded_seniority() -> list[str]:
    return list(load_career_rules()["seniority"]["too_senior_title_keywords"])


class SearchPrefsModel(BaseModel):
    """What the user edits. `countries[0]` is the home country; extra countries
    are ones they can also work from (remote roles open to them pass Stage 0)."""

    countries: list[str] = Field(default_factory=lambda: ["India"], min_length=1)
    workplace_types: list[WorkplaceType] = Field(default_factory=lambda: ["Remote"])
    remote_only: bool = False  # convenience: forces workplace_types to Remote
    # config/role_families.yaml ids (legacy RF01–RF04 accepted as aliases). Empty =
    # infer from achievements, else the user must be asked (see resolve_role_families).
    role_families: list[str] = Field(default_factory=list)
    # Adjacent families (of the chosen ones) the user opts into, e.g. a CSM open to sales.
    adjacent_families: list[str] = Field(default_factory=list)
    excluded_seniority: list[str] = Field(default_factory=_default_excluded_seniority)  # whole-word title keywords
    open_to_junior: bool = False  # newcomers / switchers: keep "Junior ..." titles and 0-2 year asks
    total_years: int = Field(3, ge=0, le=40)
    max_age_days: int = Field(30, ge=1, le=365)
    unknown_location_passes: bool = True

    @field_validator("role_families")
    @classmethod
    def _known_families(cls, value: list[str]) -> list[str]:
        unknown = [v for v in value if normalize_family(v) is None]
        if unknown:
            raise ValueError(f"unknown role families: {unknown}; see GET /role-families")
        return list(dict.fromkeys(value))

    @field_validator("adjacent_families")
    @classmethod
    def _known_adjacent(cls, value: list[str]) -> list[str]:
        unknown = [v for v in value if v not in load_taxonomy()["families"]]
        if unknown:
            raise ValueError(f"unknown role families: {unknown}; see GET /role-families")
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def _adjacent_must_be_adjacent(self) -> SearchPrefsModel:
        """Drop opt-ins that are not adjacent to a chosen family (e.g. left over after
        the user changed families) rather than failing an unrelated save."""
        chosen = normalize_families(self.role_families)
        if chosen:
            allowed = set(adjacent_of(chosen))
            self.adjacent_families = [a for a in self.adjacent_families if a in allowed]
        return self


@dataclass
class FamilyChoice:
    """The families a user's search actually runs on, and where they came from."""
    selected: list[str] = field(default_factory=list)  # v2 ids
    adjacent_opt_in: list[str] = field(default_factory=list)
    source: Literal["prefs", "achievements", "unset"] = "unset"
    inferred: list[str] = field(default_factory=list)  # suggestion from achievements, always computed

    @property
    def needs_choice(self) -> bool:
        return self.source == "unset"

    @property
    def allowed(self) -> list[str]:
        return self.selected + [a for a in self.adjacent_opt_in if a not in self.selected]


def resolve_role_families(prefs: SearchPrefsModel, index: list[dict] | None = None) -> FamilyChoice:
    """prefs first; else families inferred from the achievement index; else unset."""
    inferred = infer_families(a.get("role_families", []) for a in (index or []))
    chosen = normalize_families(prefs.role_families)
    if chosen:
        allowed_adj = set(adjacent_of(chosen))
        return FamilyChoice(chosen, [a for a in prefs.adjacent_families if a in allowed_adj], "prefs", inferred)
    if inferred:
        return FamilyChoice(inferred, [], "achievements", inferred)
    return FamilyChoice(inferred=inferred)


def load_prefs(session: Session, user_id: int) -> SearchPrefsModel:
    """Missing or partial rows fall back to defaults, so a new user can evaluate immediately."""
    row = session.get(SearchPrefs, user_id)
    return SearchPrefsModel(**(row.data or {})) if row else SearchPrefsModel()


def save_prefs(session: Session, user_id: int, prefs: SearchPrefsModel) -> SearchPrefsModel:
    row = session.get(SearchPrefs, user_id)
    if row is None:
        session.add(SearchPrefs(user_id=user_id, data=prefs.model_dump()))
    else:
        row.data = prefs.model_dump()
    session.flush()
    return prefs


def _country_aliases(country: str) -> list[str]:
    """Regexes for places inside `country` ("Toronto, ON") — config/locations.yaml."""
    table = load_yaml("locations.yaml").get("country_aliases", {})
    return list(table.get(country.strip().lower(), []))


def _junior_cap(years: int) -> int:
    """Postings whose MAX ask is at or below this are 'too junior'. years-1 for early
    careers (the shipped 3y -> 2), but only half the years for seniors: a 10-year
    marketer still wants a "5-8 years" role, just not a "1-3 years" one."""
    return max(0, years - 1) if years <= 4 else max(3, years // 2)


def rules_from_prefs(prefs: SearchPrefsModel, choice: FamilyChoice | None = None) -> dict:
    """A career_rules-shaped dict (what apply_filters/classify_job expect), built
    from the shipped file as base so every untouched rule keeps its behaviour.
    `choice` defaults to the families in prefs alone (no achievement inference)."""
    rules = copy.deepcopy(load_career_rules())
    countries = [c.strip() for c in prefs.countries if c.strip()] or ["India"]
    lowered = [c.lower() for c in countries]

    loc = rules["location"]
    loc["candidate_country"] = countries[0]
    loc["allowed_workplace_types"] = ["Remote"] if prefs.remote_only else list(prefs.workplace_types)
    loc["unknown_location_passes_through"] = prefs.unknown_location_passes
    # A "Remote - Canada" posting is only restricted AWAY from you if Canada is not yours.
    signals = [s for s in loc["eligible_signals"] if s not in _COUNTRY_SPECIFIC_SIGNALS]
    signals += [c for c in lowered if c not in signals]
    if _APAC & set(lowered):
        signals.append("apac")
    loc["eligible_signals"] = signals
    loc["location_named_regions"] = [r for r in loc["location_named_regions"] if r not in lowered]
    loc["country_aliases"] = _country_aliases(countries[0])

    years = prefs.total_years
    rules["experience"] = {
        **rules["experience"],
        "total_years": years,
        "max_required_years": years + 3,  # same slack as the shipped 3y/6y config
        "junior_cap_years": -1 if prefs.open_to_junior else _junior_cap(years),
    }
    rules["seniority"]["too_senior_title_keywords"] = list(prefs.excluded_seniority)
    if prefs.open_to_junior:
        rules["seniority"]["hard_exclude_keywords"] = [
            k for k in rules["seniority"]["hard_exclude_keywords"] if k.lower() not in _JUNIOR_TITLE_WORDS]
    rules["recency"]["max_age_days"] = prefs.max_age_days
    rules["_role_families"] = sorted(prefs.role_families)  # carried so rules_signature sees it
    choice = choice if choice is not None else resolve_role_families(prefs)
    if choice.selected:
        _apply_taxonomy(rules, choice)
    return rules


def _apply_taxonomy(rules: dict, choice: FamilyChoice) -> None:
    """Swap the AI/ML-specific title rules and role_type gate for the user's families."""
    allowed = choice.allowed
    rules["family_filter"] = family_filter(allowed)
    rules["role_taxonomy"] = {
        "version": 2,
        "digest": taxonomy_digest(),
        "selected": list(choice.selected),
        "adjacent_opt_in": [a for a in choice.adjacent_opt_in if a not in choice.selected],
        # the model may name any adjacent family, so a near-miss is labelled honestly and then gated
        "prompt_families": list(choice.selected) + adjacent_of(choice.selected),
    }
    rules["ai_gates"] = {**rules["ai_gates"], "allowed_families": allowed}
    rules["title_signals"] = {}
    rules["hard_exclusions"] = {
        **rules["hard_exclusions"],
        "title_keywords": [k for k in rules["hard_exclusions"]["title_keywords"]
                           if k.lower() in _ELIGIBILITY_TITLE_EXCLUSIONS],
    }
    rules["seniority"]["not_too_senior"] = not_too_senior_phrases(allowed)
    rules["keyword_weights"] = vocab_weights(allowed)
    rules["_role_families"] = sorted(allowed)


def roles_for_choice(prefs: SearchPrefsModel, choice: FamilyChoice) -> dict:
    """The `roles` dict for classify_job: taxonomy v2 families when chosen, else legacy roles.yaml."""
    if not choice.selected:
        return roles_from_prefs(prefs)
    families = load_taxonomy()["families"]
    return {"role_families": {fid: copy.deepcopy(families[fid]) for fid in choice.allowed}}


def roles_from_prefs(prefs: SearchPrefsModel) -> dict:
    """Legacy: roles.yaml restricted to the user's chosen RF ids (used only while the
    user has no taxonomy-v2 families, i.e. the pre-taxonomy AI/ML default)."""
    roles = copy.deepcopy(load_roles())
    if prefs.role_families:
        chosen = {k: v for k, v in roles["role_families"].items() if k in set(prefs.role_families)}
        roles["role_families"] = chosen or roles["role_families"]  # unknown ids must not empty the taxonomy
    return roles


def achievement_index(session: Session, user_id: int) -> list[dict]:
    """Achievement rows in the exact dict shape of data/achievements_index.yaml,
    so retrieve_achievements scores them unchanged. Ids are `A<row id>`."""
    rows = session.scalars(select(Achievement).where(Achievement.user_id == user_id).order_by(Achievement.id)).all()
    out = []
    for row in rows:
        entry = {"id": f"A{row.id}", "title": row.title, "summary": row.summary or ""}
        fields = row.fields or {}
        for key in _LIST_FIELDS:
            entry[key] = [str(v) for v in (fields.get(key) or [])]
        # Add the taxonomy-v2 id for each free-text tag ("data_engineering" -> data_analytics)
        # so retrieval matches the classifier's role_family; originals are kept.
        entry["role_families"] += [f for f in normalize_families(entry["role_families"], fuzzy=True)
                                   if f not in entry["role_families"]]
        out.append(entry)
    return out


def profile_from_user(session: Session, user_id: int, prefs: SearchPrefsModel | None = None) -> dict:
    """{summary, baseline_skills} for the prompts, with no LLM call: the summary
    is assembled from the user's own evidence bank and prefs."""
    prefs = prefs or load_prefs(session, user_id)
    index = achievement_index(session, user_id)
    skill_counts = Counter(s for a in index for s in a["skills"])
    top_skills = [s for s, _ in skill_counts.most_common(30)]
    work = "; ".join(a["title"] for a in index[:6])
    where = ", ".join(prefs.countries)
    modes = "remote" if prefs.remote_only else "/".join(w.lower() for w in prefs.workplace_types)
    parts = [f"Candidate with about {prefs.total_years} years of experience."]
    if work:
        parts.append(f"Key work: {work}.")
    if top_skills:
        parts.append(f"Core skills: {', '.join(top_skills[:12])}.")
    parts.append(f"Based in {where}; wants {modes} roles.")
    return {"summary": " ".join(parts), "baseline_skills": ", ".join(top_skills) or "(none recorded)"}


def rules_signature(rules: dict, profile: dict, models_cfg: dict | None = None) -> str:
    """Hash of everything that shapes a verdict: user rules, profile, prompts and
    the vetting model routes. Any change invalidates that user's cached verdicts.
    Stage-0 inputs are included because filtered outcomes are cached too."""
    models_cfg = models_cfg if models_cfg is not None else load_models()
    keys = ("location", "recency", "experience", "ai_gates", "title_signals", "seniority",
            "hard_exclusions", "employment_type", "_role_families")
    if rules.get("role_taxonomy"):  # taxonomy v2: families, their signals and the v3 prompt
        keys += ("family_filter", "role_taxonomy")
    triage_prompt = "classify_job_v3.txt" if rules.get("role_taxonomy") else "classify_job_v2.txt"
    parts = [
        json.dumps(profile, sort_keys=True),
        json.dumps({k: rules.get(k) for k in keys}, sort_keys=True),
        (PROMPTS_DIR / triage_prompt).read_text(encoding="utf-8"),
        (PROMPTS_DIR / "analyse_match_v3.txt").read_text(encoding="utf-8"),
        json.dumps({k: models_cfg["routing"][k] for k in ("classify_job", "analyse_match")}, sort_keys=True),
    ]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]
