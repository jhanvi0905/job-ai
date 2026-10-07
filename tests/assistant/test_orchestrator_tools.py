"""tools.py wrappers: success -> distilled CapabilityCall, failure -> status="failed" without raising."""
from unittest.mock import patch

from jobai.assistant.orchestrator import tools
from jobai.assistant.workflows.inbox import InboxSummary
from jobai.core.telemetry.logging import RunSummary
from jobai.engine.jobs.schemas import JobMatch


def test_call_discover_jobs_success():
    summary = RunSummary(run_id="run-1", new_candidates=5, written_to_notion=2)
    with patch("jobai.assistant.orchestrator.tools.capabilities.discover_jobs", return_value=summary):
        result = tools.call_discover_jobs()
    assert result == {
        "name": "discover_jobs",
        "args": {},
        "result_summary": "5 candidates evaluated, 2 written to Notion",
        "ledger_run_id": "run-1",
        "status": "ok",
    }


def test_call_discover_jobs_failure_does_not_raise():
    with patch("jobai.assistant.orchestrator.tools.capabilities.discover_jobs", side_effect=RuntimeError("boom")):
        result = tools.call_discover_jobs()
    assert result["status"] == "failed"
    assert "boom" in result["result_summary"]
    assert result["ledger_run_id"] is None


def test_call_analyse_job_success():
    match = JobMatch(fit_band="strong", priority="P1", reason="x", run_id="run-2")
    with patch("jobai.assistant.orchestrator.tools.capabilities.analyse_job", return_value=match):
        result = tools.call_analyse_job("greenhouse:1")
    assert result == {
        "name": "analyse_job",
        "args": {"job_fingerprint": "greenhouse:1"},
        "result_summary": "strong fit, priority P1",
        "ledger_run_id": "run-2",
        "status": "ok",
    }


def test_call_analyse_job_failure_does_not_raise():
    with patch("jobai.assistant.orchestrator.tools.capabilities.analyse_job", side_effect=ValueError("no such page")):
        result = tools.call_analyse_job("greenhouse:999")
    assert result["status"] == "failed"
    assert "no such page" in result["result_summary"]
    assert result["args"] == {"job_fingerprint": "greenhouse:999"}


def test_call_get_priority_jobs_success():
    jobs = [{"Opportunity": "AI Engineer"}, {"Opportunity": "ML Engineer"}]
    with patch("jobai.assistant.orchestrator.tools.capabilities.get_priority_jobs", return_value=jobs):
        result = tools.call_get_priority_jobs(limit=5)
    assert result == {
        "name": "get_priority_jobs",
        "args": {"limit": 5},
        "result_summary": "2 jobs in review queue",
        "ledger_run_id": None,
        "status": "ok",
    }


def test_call_get_priority_jobs_failure_does_not_raise():
    with patch("jobai.assistant.orchestrator.tools.capabilities.get_priority_jobs", side_effect=RuntimeError("notion down")):
        result = tools.call_get_priority_jobs()
    assert result["status"] == "failed"
    assert result["ledger_run_id"] is None


def test_call_sync_inbox_success():
    summary = InboxSummary(run_id="run-3", processed=4, updates=["a -> Applied", "b -> Rejected"])
    with patch("jobai.assistant.orchestrator.tools.capabilities.sync_inbox", return_value=summary):
        result = tools.call_sync_inbox(dry_run=True, lookback_days=7)
    assert result == {
        "name": "sync_inbox",
        "args": {"dry_run": True, "lookback_days": 7},
        "result_summary": "4 emails processed, 2 status updates",
        "ledger_run_id": "run-3",
        "status": "ok",
    }


def test_call_sync_inbox_failure_does_not_raise():
    with patch("jobai.assistant.orchestrator.tools.capabilities.sync_inbox", side_effect=RuntimeError("gmail auth failed")):
        result = tools.call_sync_inbox()
    assert result["status"] == "failed"
    assert "gmail auth failed" in result["result_summary"]
