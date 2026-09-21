"""Callable capabilities (PRD §25) — the seam a future LifeOS master
assistant calls, through whatever transport it uses later (MCP, an HTTP
handler, a LangChain/LangGraph tool wrapper — the transport is someone else's
problem). Everything here is a plain, typed, independently-callable function.
None of it loops, decides its own next step, or calls itself — it's not an
agent, it's a small set of capabilities an agent (or a human, or a cron job)
can call.

Only analyse_job() spends AI tokens, and only for the one job you name.
"""
from __future__ import annotations

from datetime import date

from src.achievements.retrieval import retrieve_achievements
from src.ai.classifier import classify_job
from src.ai.matcher import analyse_match
from src.ai.role_labels import ROLE_FAMILY_LABELS
from src.integrations.notion import NotionClient
from src.jobs.refetch import refetch_job
from src.jobs.schemas import JobMatch
from src.telemetry.logging import RunSummary
from src.workflows.process_job import run as _run_discovery

_RECOMMENDED_ACTION_TO_STATUS = {"review": "Shortlisted", "watch": "Watch", "reject": "Rejected"}


def discover_jobs() -> RunSummary:
    """Fetch every configured source, dedupe against Notion, deterministically
    filter, and write survivors to Notion as 'Discovered'. Zero AI calls —
    safe to run as often as you like."""
    return _run_discovery()


def analyse_job(job_fingerprint: str) -> JobMatch:
    """Run Stage 1 (cheap triage) + Stage 2 (achievement retrieval) + Stage 3
    (deep match) for ONE already-discovered job, and write the result back to
    its Notion page. Raises if the job isn't in Notion or is no longer posted."""
    notion = NotionClient()
    page = notion.get_plain_by_fingerprint(job_fingerprint)
    if page is None:
        raise ValueError(f"No Notion page found for job_fingerprint={job_fingerprint!r}")

    source_type = job_fingerprint.split(":", 1)[0]
    job = refetch_job(page["Company"], source_type, job_fingerprint.split(":", 1)[1])

    classification = classify_job(job)
    achievements = retrieve_achievements(classification.role_family, classification.key_requirements)
    match = analyse_match(job, classification.key_requirements, achievements)

    notion.update_job_page(
        page["notion_page_id"],
        {
            "Role Family": ROLE_FAMILY_LABELS.get(classification.role_family),
            "Seniority": classification.seniority,
            "Fit Band": match.fit_band.capitalize(),
            "Priority": match.priority,
            "Matched Achievements": ", ".join(a.id for a in match.matched_achievements),
            "Strong Evidence": "; ".join(match.strong_evidence),
            "Partial Evidence": "; ".join(match.partial_evidence),
            "Gaps": "; ".join(match.gaps),
            "Why It Fits": match.reason,
            "Status": _RECOMMENDED_ACTION_TO_STATUS.get(match.recommended_action, "Shortlisted"),
            "Last Analysed": date.today().isoformat(),
        },
    )
    return match


def get_priority_jobs(limit: int = 15) -> list[dict]:
    """Read-only: today's 'Jobs to Review' queue, sorted by Priority then
    Date Posted (PRD §37) — what a daily briefing would surface."""
    notion = NotionClient()
    return notion.query_priority_jobs(limit=limit)
