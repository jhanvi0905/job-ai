"""Stage 2 — deterministic achievement retrieval (PRD §16). Weighted tag
overlap; no embeddings, no vector DB — add those only if this measurably
fails to retrieve obvious matches (PRD §45 kill criteria)."""
from __future__ import annotations

from dataclasses import dataclass, field

from src.achievements.loader import load_achievement_index

# Field weights: role-family and skill matches count more than loose
# business/leadership phrase overlap.
FIELD_WEIGHTS = {
    "role_families": 3,
    "skills": 3,
    "system_patterns": 2,
    "seniority_signals": 1,
    "business_signals": 1,
    "leadership_signals": 1,
}


@dataclass
class RetrievedAchievement:
    id: str
    title: str
    score: int
    matched_terms: list[str]
    summary: str = ""
    skills: list[str] = field(default_factory=list)
    system_patterns: list[str] = field(default_factory=list)


def _terms_from_requirements(key_requirements: list[str]) -> set[str]:
    terms: set[str] = set()
    for req in key_requirements:
        terms.add(req.lower().strip())
    return terms


def retrieve_achievements(
    role_family: str | None,
    key_requirements: list[str],
    top_k: int = 5,
) -> list[RetrievedAchievement]:
    requirement_terms = _terms_from_requirements(key_requirements)
    scored: list[RetrievedAchievement] = []

    for achievement in load_achievement_index():
        score = 0
        matched: list[str] = []

        if role_family and role_family in achievement.get("role_families", []):
            score += FIELD_WEIGHTS["role_families"]
            matched.append(role_family)

        for field, weight in FIELD_WEIGHTS.items():
            if field == "role_families":
                continue
            for value in achievement.get(field, []):
                value_lower = value.lower()
                if any(term in value_lower or value_lower in term for term in requirement_terms):
                    score += weight
                    matched.append(value)

        if score > 0:
            scored.append(
                RetrievedAchievement(
                    id=achievement["id"],
                    title=achievement["title"],
                    score=score,
                    matched_terms=matched,
                    summary=achievement.get("summary", ""),
                    skills=achievement.get("skills", []),
                    system_patterns=achievement.get("system_patterns", []),
                )
            )

    scored.sort(key=lambda r: r.score, reverse=True)
    top = scored[:top_k]

    # Never hand the matcher an empty evidence set: sparse tag overlap is a
    # retrieval limitation, not proof the candidate has nothing relevant. Top
    # up to 3 with achievements from the job's own role family.
    floor = min(3, top_k)
    if len(top) < floor and role_family:
        have = {r.id for r in top}
        for achievement in load_achievement_index():
            if len(top) >= floor:
                break
            if achievement["id"] not in have and role_family in achievement.get("role_families", []):
                top.append(
                    RetrievedAchievement(
                        id=achievement["id"],
                        title=achievement["title"],
                        score=0,
                        matched_terms=[role_family],
                        summary=achievement.get("summary", ""),
                        skills=achievement.get("skills", []),
                        system_patterns=achievement.get("system_patterns", []),
                    )
                )
    return top
