"""Stage 1 — AI triage (PRD §15). One structured call per Stage-0 survivor.

The prompt carries a short professional profile of the candidate and the
years they have, so fit is judged against a real person, not "an AI engineer"
in the abstract. The model's `relevant` verdict is never trusted directly: it
is derived here from role_type / fit / hard_blocker against the ai_gates in
config/career_rules.yaml.
"""
from __future__ import annotations

from pathlib import Path

from src.ai.provider import LLMProvider
from src.config import load_candidate_profile, load_career_rules, load_models, load_roles
from src.jobs.experience import extract_required_years
from src.jobs.schemas import JobClassification, NormalizedJob

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "classify_job_v2.txt"
MAX_DESCRIPTION_CHARS = 4000  # keep Stage 1 input small and cheap

FIT_RANK = {"no": 0, "weak": 1, "plausible": 2, "strong": 3}


def classify_job(job: NormalizedJob, provider: LLMProvider) -> JobClassification:
    routing = load_models()["routing"]["classify_job"]
    rules = load_career_rules()

    years = rules["experience"]["total_years"]
    # Years never go to the model: it applies them inconsistently. Regex
    # extracts the ask, cap_fit_by_years() applies the rule in code.
    req = extract_required_years(job.description)
    prompt = PROMPT_PATH.read_text(encoding="utf-8").format(
        candidate=" ".join(load_candidate_profile()["summary"].split()),
        role_taxonomy=_compact_taxonomy(load_roles()),
        title=job.title,
        company=job.company_name,
        location=job.location or "Unknown",
        description=job.description[:MAX_DESCRIPTION_CHARS],
    )

    raw = provider._chat(  # noqa: SLF001 — internal, single call site by design
        model=routing["model"],
        messages=[{"role": "user", "content": prompt}],
        max_tokens=routing["max_output_tokens"],
        temperature=routing["temperature"],
        workflow="classify_job",
        job_id=job.job_fingerprint or job.external_job_id,
        prompt_version="classify_job_v2",
        context={"jd_chars_sent": min(len(job.description), MAX_DESCRIPTION_CHARS),
                 "jd_truncated": len(job.description) > MAX_DESCRIPTION_CHARS},
        validate=_validate_classification,
    )
    # The regex figure is a fact from the posting; the model's is a guess.
    if req:
        raw["min_years_required"] = req.min_years
    raw["fit"] = cap_fit_by_years(raw.get("fit"), raw.get("min_years_required"), years)
    raw["relevant"] = _is_relevant(raw, rules["ai_gates"])
    return JobClassification(**raw)


def _validate_classification(raw: dict) -> None:
    """Strict enough that a missing verdict is repaired, not silently read as 'no'."""
    missing = [k for k in ("role_type", "fit") if raw.get(k) in (None, "")]
    if missing:
        raise ValueError(f"missing required field(s): {', '.join(missing)}")
    JobClassification(**{**raw, "relevant": False})  # enum/type checks (fit must be strong|plausible|weak|no)


def cap_fit_by_years(fit: str | None, required: int | None, candidate_years: int) -> str | None:
    """Enforce the years rule in code so it can't drift with model mood:
    asks within 1 year of yours -> no cap; 2-3 above -> at most plausible;
    4+ above -> at most weak."""
    if fit is None or required is None:
        return fit
    gap = required - candidate_years
    ceiling = "weak" if gap >= 4 else "plausible" if gap >= 2 else "strong"
    return fit if FIT_RANK.get(fit, 0) <= FIT_RANK[ceiling] else ceiling


def _is_relevant(raw: dict, gates: dict) -> bool:
    fit = raw.get("fit")
    return (
        raw.get("role_type") in gates["allowed_role_types"]
        and FIT_RANK.get(fit, 0) >= FIT_RANK[gates["min_classifier_fit"]]
        and not raw.get("hard_blocker", False)
    )


def _compact_taxonomy(roles: dict) -> str:
    lines = []
    for family_id, family in roles["role_families"].items():
        lines.append(f"{family_id}: {family['name']} — signals: {', '.join(family['signals'])}")
    return "\n".join(lines)
