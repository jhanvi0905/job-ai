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

from jobai.assistant.integrations.job_record import evaluation_properties
from jobai.assistant.integrations.notion import NotionClient
from jobai.assistant.workflows.inbox import InboxSummary
from jobai.assistant.workflows.inbox import run as _run_inbox_sync
from jobai.assistant.workflows.process_job import run as _run_discovery
from jobai.core.config import load_models
from jobai.core.ledger.db import Ledger
from jobai.core.telemetry.logging import RunSummary
from jobai.engine.achievements.retrieval import retrieve_achievements
from jobai.engine.ai.classifier import classify_job
from jobai.engine.ai.matcher import analyse_match
from jobai.engine.ai.provider import LLMProvider
from jobai.engine.jobs.decisions import rules_signature
from jobai.engine.jobs.refetch import refetch_job
from jobai.engine.jobs.schemas import JobMatch

# "review" leaves Status alone (a reviewed-worthy job is already "Discovered"
# and the user may have moved it since); only watch/reject change it.
_RECOMMENDED_ACTION_TO_STATUS = {"watch": "Watch", "reject": "Rejected"}


def discover_jobs(dry_run: bool = False) -> RunSummary:
    """Fetch every configured source, filter and dedupe for free, have the AI
    vet what's left (triage + match against your achievements), and write only
    the jobs it approves to Notion as 'Discovered'. dry_run previews without writing."""
    return _run_discovery(dry_run=dry_run)


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

    ledger = Ledger()
    run_id = ledger.start_run(
        "analyse_job", budget_usd=load_models().get("budget", {}).get("per_run_usd"),
        config_signature=rules_signature(),
    )
    provider = LLMProvider(ledger, run_id)
    status, note = "ok", None
    try:
        classification = classify_job(job, provider)
        achievements = retrieve_achievements(classification.role_family, classification.key_requirements)
        match = analyse_match(
            job, classification.key_requirements, achievements, provider, classification=classification
        )
    except Exception as exc:
        status, note = "failed", f"{type(exc).__name__}: {exc}"[:300]
        raise
    finally:
        ledger.finish_run(run_id, status, note)
        ledger.close()

    properties = evaluation_properties(classification, match)
    properties["Status"] = _RECOMMENDED_ACTION_TO_STATUS.get(match.recommended_action)
    notion.update_job_page(page["notion_page_id"], properties)
    match.run_id = run_id
    return match


def sync_inbox(dry_run: bool = False, lookback_days: int = 3) -> InboxSummary:
    """Scan recent Gmail for replies to tracked applications and update their
    Notion status accordingly."""
    return _run_inbox_sync(dry_run=dry_run, lookback_days=lookback_days)


def get_priority_jobs(limit: int = 15) -> list[dict]:
    """Read-only: today's 'Jobs to Review' queue, sorted by Priority then
    Date Posted (PRD §37) — what a daily briefing would surface."""
    notion = NotionClient()
    return notion.query_priority_jobs(limit=limit)
