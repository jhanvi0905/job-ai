"""Stage 1 — cheap AI classification (PRD §15). NOT wired into the Phase 1
workflow yet; this is the Phase 2 seam. Sends only title/company/location/JD
excerpt + role taxonomy — never the achievement bank."""
from __future__ import annotations

from pathlib import Path

from src.ai.provider import LLMProvider
from src.config import load_models, load_roles
from src.jobs.schemas import JobClassification, NormalizedJob

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "classify_job_v1.txt"
MAX_DESCRIPTION_CHARS = 4000  # keep Stage 1 input small and cheap


def classify_job(job: NormalizedJob, provider: LLMProvider | None = None) -> JobClassification:
    provider = provider or LLMProvider()
    routing = load_models()["routing"]["classify_job"]
    roles = load_roles()

    prompt = PROMPT_PATH.read_text(encoding="utf-8").format(
        role_taxonomy=_compact_taxonomy(roles),
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
    )
    return JobClassification(**raw)


def _compact_taxonomy(roles: dict) -> str:
    lines = []
    for family_id, family in roles["role_families"].items():
        lines.append(f"{family_id}: {family['name']} — signals: {', '.join(family['signals'])}")
    return "\n".join(lines)
