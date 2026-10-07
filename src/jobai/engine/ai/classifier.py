"""Stage 1 — AI triage (PRD §15). One structured call per Stage-0 survivor.

The prompt carries a short professional profile of the candidate and the
years they have, so fit is judged against a real person, not "an AI engineer"
in the abstract. The model's `relevant` verdict is never trusted directly: it
is derived here from role_type / fit / hard_blocker against the ai_gates in
config/career_rules.yaml.

Two prompt versions:
  * classify_job_v2 — the legacy single-user pipeline (roles.yaml RF01–RF04, role_type gate);
  * classify_job_v3 — the product path, chosen when `rules["role_taxonomy"]` is present
    (built by product.services.prefs from config/role_families.yaml). role_family is a
    v2 family id and the gate is "family in the user's selected + opted-in adjacent families".
"""
from __future__ import annotations

from jobai.core.config import load_candidate_profile, load_career_rules, load_models, load_roles
from jobai.core.paths import PROMPTS_DIR
from jobai.engine.ai.provider import LLMProvider
from jobai.engine.jobs.experience import extract_required_years
from jobai.engine.jobs.role_taxonomy import OTHER, compact_taxonomy, normalize_family
from jobai.engine.jobs.schemas import JobClassification, NormalizedJob

PROMPT_PATH = PROMPTS_DIR / "classify_job_v2.txt"
PROMPT_V3_PATH = PROMPT_PATH.with_name("classify_job_v3.txt")
GIG_ROLE_TYPE = "gig_or_task_work"
MAX_DESCRIPTION_CHARS = 4000  # keep Stage 1 input small and cheap

FIT_RANK = {"no": 0, "weak": 1, "plausible": 2, "strong": 3}


def classify_job(
    job: NormalizedJob,
    provider: LLMProvider,
    *,
    profile: dict | None = None,
    rules: dict | None = None,
    roles: dict | None = None,
) -> JobClassification:
    """`profile`/`rules`/`roles` default to the single-tenant config files; the
    multi-tenant product passes per-user equivalents instead."""
    routing = load_models()["routing"]["classify_job"]
    rules = rules if rules is not None else load_career_rules()
    profile = profile if profile is not None else load_candidate_profile()
    roles = roles if roles is not None else load_roles()

    years = rules["experience"]["total_years"]
    # Years never go to the model: it applies them inconsistently. Regex
    # extracts the ask, cap_fit_by_years() applies the rule in code.
    req = extract_required_years(job.description)
    taxonomy = rules.get("role_taxonomy")
    prompt, version = build_prompt(job, profile, roles, taxonomy)

    raw = provider._chat(  # noqa: SLF001 — internal, single call site by design
        model=routing["model"],
        messages=[{"role": "user", "content": prompt}],
        max_tokens=routing["max_output_tokens"],
        temperature=routing["temperature"],
        workflow="classify_job",
        job_id=job.job_fingerprint or job.external_job_id,
        prompt_version=version,
        context={"jd_chars_sent": min(len(job.description), MAX_DESCRIPTION_CHARS),
                 "jd_truncated": len(job.description) > MAX_DESCRIPTION_CHARS},
        validate=_validate_classification,
    )
    if taxonomy:
        raw["role_family"] = normalize_family(raw.get("role_family")) or OTHER
    # The regex figure is a fact from the posting; the model's is a guess.
    if req:
        raw["min_years_required"] = req.min_years
    raw["fit"] = cap_fit_by_years(raw.get("fit"), raw.get("min_years_required"), years)
    raw["relevant"] = _is_relevant(raw, rules["ai_gates"])
    return JobClassification(**raw)


def build_prompt(job: NormalizedJob, profile: dict, roles: dict, taxonomy: dict | None) -> tuple[str, str]:
    """(prompt text, prompt version). Pure, so prompt size is testable offline."""
    common = {
        "candidate": " ".join(profile["summary"].split()),
        "title": job.title,
        "company": job.company_name,
        "location": job.location or "Unknown",
        "description": job.description[:MAX_DESCRIPTION_CHARS],
    }
    if taxonomy:
        text = PROMPT_V3_PATH.read_text(encoding="utf-8").format(
            wanted=_wanted_line(taxonomy), role_taxonomy=compact_taxonomy(taxonomy["prompt_families"]), **common)
        return text, "classify_job_v3"
    text = PROMPT_PATH.read_text(encoding="utf-8").format(role_taxonomy=_compact_taxonomy(roles), **common)
    return text, "classify_job_v2"


def _wanted_line(taxonomy: dict) -> str:
    line = ", ".join(taxonomy["selected"])
    if taxonomy.get("adjacent_opt_in"):
        line += f" (also open to: {', '.join(taxonomy['adjacent_opt_in'])})"
    return line


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
        _kind_allowed(raw.get("role_type"), raw.get("role_family"), gates)
        and FIT_RANK.get(fit, 0) >= FIT_RANK[gates["min_classifier_fit"]]
        and not raw.get("hard_blocker", False)
    )


def _kind_allowed(role_type: str | None, role_family: str | None, gates: dict) -> bool:
    """Product gates carry `allowed_families` (taxonomy v2); legacy gates gate on role_type."""
    if "allowed_families" in gates:
        return role_family in gates["allowed_families"] and role_type != GIG_ROLE_TYPE
    return role_type in gates["allowed_role_types"]


def triage_reject_code(verdict: JobClassification, gates: dict) -> str:
    """Same codes as process_job._triage_reject_code, for either gate shape."""
    if verdict.hard_blocker:
        return "rejected_blocker"
    if not _kind_allowed(verdict.role_type, verdict.role_family, gates):
        return "rejected_role_type"
    return "rejected_fit_low"


def _compact_taxonomy(roles: dict) -> str:
    lines = []
    for family_id, family in roles["role_families"].items():
        lines.append(f"{family_id}: {family['name']} — signals: {', '.join(family['signals'])}")
    return "\n".join(lines)
