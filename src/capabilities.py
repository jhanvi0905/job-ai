"""Callable capabilities (PRD §25) — the seam a future LifeOS master
assistant calls, through whatever transport it uses later (MCP, an HTTP
handler, a LangChain/LangGraph tool wrapper — the transport is someone else's
problem). Everything here is a plain, typed, independently-callable function.
None of it loops, decides its own next step, or calls itself — it's not an
agent, it's a small set of capabilities an agent (or a human, or a cron job)
can call.

discover_jobs() spends AI tokens only on jobs that survive the free Stage-0
filters; analyse_job() spends them on the one job you name.
"""
from __future__ import annotations

from src.achievements.retrieval import retrieve_achievements
from src.ai.classifier import classify_job
from src.ai.matcher import analyse_match
from src.integrations.job_record import evaluation_properties
from src.integrations.notion import NotionClient
from src.jobs.refetch import refetch_job
from src.jobs.schemas import JobMatch
from src.telemetry.logging import RunSummary
from src.workflows.process_job import run as _run_discovery

# "review" leaves Status alone (a reviewed-worthy job is already "Discovered"
# and the user may have moved it since); only watch/reject change it.
_RECOMMENDED_ACTION_TO_STATUS = {"watch": "Watch", "reject": "Rejected"}


def discover_jobs() -> RunSummary:
    """Fetch every configured source, filter and dedupe for free, have the AI
    vet what's left (triage + match against your achievements), and write only
    the jobs it approves to Notion as 'Discovered'."""
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
    match = analyse_match(
        job, classification.key_requirements, achievements, classification=classification
    )

    properties = evaluation_properties(classification, match)
    properties["Status"] = _RECOMMENDED_ACTION_TO_STATUS.get(match.recommended_action)
    notion.update_job_page(page["notion_page_id"], properties)
    return match


def get_priority_jobs(limit: int = 15) -> list[dict]:
    """Read-only: today's 'Jobs to Review' queue, sorted by Priority then
    Date Posted (PRD §37) — what a daily briefing would surface."""
    notion = NotionClient()
    return notion.query_priority_jobs(limit=limit)
