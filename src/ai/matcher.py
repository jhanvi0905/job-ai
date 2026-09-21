"""Stage 3 — deep job/evidence match analysis (PRD §17). NOT wired into the
Phase 1 workflow yet; Phase 3 seam. Only the top-k retrieved achievements are
sent — never the full achievement index."""
from __future__ import annotations

from pathlib import Path

from src.achievements.retrieval import RetrievedAchievement
from src.ai.provider import LLMProvider
from src.config import load_models
from src.jobs.schemas import JobMatch, NormalizedJob

PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "prompts" / "analyse_match_v1.txt"


def analyse_match(
    job: NormalizedJob,
    key_requirements: list[str],
    achievements: list[RetrievedAchievement],
    provider: LLMProvider | None = None,
) -> JobMatch:
    provider = provider or LLMProvider()
    routing = load_models()["routing"]["analyse_match"]

    prompt = PROMPT_PATH.read_text(encoding="utf-8").format(
        key_requirements="\n".join(f"- {r}" for r in key_requirements),
        achievements="\n".join(
            f"- {a.id} ({a.title}): matched on {', '.join(a.matched_terms)}" for a in achievements
        ),
    )

    raw = provider._chat(  # noqa: SLF001
        model=routing["model"],
        messages=[{"role": "user", "content": prompt}],
        max_tokens=routing["max_output_tokens"],
        temperature=routing["temperature"],
        workflow="analyse_match",
        job_id=job.job_fingerprint or job.external_job_id,
    )
    return JobMatch(**raw)
