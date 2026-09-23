"""Stage 3 — deep job/evidence match analysis (PRD §17). Only the top-k
retrieved achievements are sent — never the full achievement index."""
from __future__ import annotations

from pathlib import Path

from src.achievements.retrieval import RetrievedAchievement
from src.ai.provider import LLMProvider
from src.config import load_candidate_profile, load_models
from src.jobs.schemas import JobClassification, JobMatch, NormalizedJob

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "analyse_match_v3.txt"

_EVIDENCE_TO_STRENGTH = {"direct": "strong", "adjacent": "plausible"}


def analyse_match(
    job: NormalizedJob,
    key_requirements: list[str],
    achievements: list[RetrievedAchievement],
    provider: LLMProvider | None = None,
    classification: JobClassification | None = None,
) -> JobMatch:
    """The model judges each requirement (direct / adjacent / none); the fit
    band, priority and gaps are then computed in code from those judgments —
    so "strong" means something specific and every gap is a requirement the
    model actually found unsupported."""
    provider = provider or LLMProvider()
    routing = load_models()["routing"]["analyse_match"]

    prompt = PROMPT_PATH.read_text(encoding="utf-8").format(
        achievements="\n".join(_format_achievement(a) for a in achievements) or "- (none retrieved)",
        baseline_skills=" ".join(load_candidate_profile()["baseline_skills"].split()),
        job_context=_job_context(job, classification, key_requirements),
    )

    raw = provider._chat(  # noqa: SLF001
        model=routing["model"],
        messages=[{"role": "user", "content": prompt}],
        max_tokens=routing["max_output_tokens"],
        temperature=routing["temperature"],
        workflow="analyse_match",
        job_id=job.job_fingerprint or job.external_job_id,
    )
    return score_match(raw)


def score_match(raw: dict) -> JobMatch:
    reqs = [r for r in raw.get("requirements", []) if r.get("req")]
    core = [r for r in reqs if r.get("importance") == "core"] or reqs  # no tagging -> treat all as core

    def n(items, ev):
        return sum(1 for r in items if r.get("evidence") == ev)

    core_total = len(core)
    core_direct, core_adjacent, core_none = n(core, "direct"), n(core, "adjacent"), n(core, "none")

    if raw.get("blocker"):
        band = "blocked"
    elif core_total == 0:
        band = "weak"
    elif core_direct / core_total >= 0.7 and core_none == 0:
        band = "strong"
    elif (core_direct + core_adjacent) / core_total >= 0.6 and core_none <= 1:
        band = "plausible"
    else:
        band = "weak"

    achievements: dict[str, str] = {}
    for r in reqs:
        strength = _EVIDENCE_TO_STRENGTH.get(r.get("evidence"))
        for aid in r.get("achievement_ids") or []:
            if strength and (aid not in achievements or strength == "strong"):
                achievements[aid] = strength

    return JobMatch(
        fit_band=band,
        priority={"strong": "P1", "plausible": "P2"}.get(band, "P3"),
        matched_achievements=[
            {"id": aid, "strength": st, "supports": [r["req"] for r in reqs if aid in (r.get("achievement_ids") or [])]}
            for aid, st in achievements.items()
        ],
        strong_evidence=[r["req"] for r in reqs if r.get("evidence") == "direct"],
        partial_evidence=[r["req"] for r in reqs if r.get("evidence") == "adjacent"],
        gaps=[r["req"] for r in sorted(reqs, key=lambda r: r.get("importance") != "core") if r.get("evidence") == "none"],
        reason=raw.get("reason", ""),
        recommended_action="review" if band in ("strong", "plausible") else "reject",
    )


def _format_achievement(a: RetrievedAchievement) -> str:
    # The compact evidence record (PRD §8: ~50-150 tokens each), not just tag
    # names — the model can only judge "evidence for X" from what it can read.
    tech = ", ".join(a.skills[:10])
    return f"- {a.id} {a.title}: {a.summary} Tech: {tech}."


def _job_context(job: NormalizedJob, c: JobClassification | None, key_requirements: list[str]) -> str:
    # No years here either: the years rule is enforced in code after the call.
    lines = [f"Title: {job.title} at {job.company_name}"]
    if c is not None and c.seniority:
        lines.append(f"Level: {c.seniority}")
    lines.append("Description (may be truncated):\n" + job.description[:3500])
    return "\n".join(lines)
