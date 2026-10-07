"""One wrapper per jobai.assistant.capabilities function, turning a plain call into a
CapabilityCall record the graph can append to state. Exceptions from the
capability are caught here (fail-per-call isolation, same spirit as
write_to_notion's per-item try/except) so one bad call never crashes the
graph — it just shows up as status="failed" for the routing step to see.
"""
from __future__ import annotations

from jobai.assistant import capabilities
from jobai.assistant.orchestrator.state import CapabilityCall


def _failed(name: str, args: dict, exc: Exception) -> CapabilityCall:
    return {
        "name": name,
        "args": args,
        "result_summary": f"{type(exc).__name__}: {exc}"[:300],
        "ledger_run_id": None,
        "status": "failed",
    }


def call_discover_jobs() -> CapabilityCall:
    try:
        summary = capabilities.discover_jobs()
    except Exception as exc:  # noqa: BLE001
        return _failed("discover_jobs", {}, exc)
    return {
        "name": "discover_jobs",
        "args": {},
        "result_summary": f"{summary.new_candidates} candidates evaluated, {summary.written_to_notion} written to Notion",
        "ledger_run_id": summary.run_id,
        "status": "ok",
    }


def call_analyse_job(job_fingerprint: str) -> CapabilityCall:
    args = {"job_fingerprint": job_fingerprint}
    try:
        match = capabilities.analyse_job(job_fingerprint)
    except Exception as exc:  # noqa: BLE001
        return _failed("analyse_job", args, exc)
    return {
        "name": "analyse_job",
        "args": args,
        "result_summary": f"{match.fit_band} fit, priority {match.priority}",
        "ledger_run_id": match.run_id,
        "status": "ok",
    }


def call_get_priority_jobs(limit: int = 15) -> CapabilityCall:
    args = {"limit": limit}
    try:
        jobs = capabilities.get_priority_jobs(limit=limit)
    except Exception as exc:  # noqa: BLE001
        return _failed("get_priority_jobs", args, exc)
    return {
        "name": "get_priority_jobs",
        "args": args,
        "result_summary": f"{len(jobs)} jobs in review queue",
        "ledger_run_id": None,
        "status": "ok",
    }


def call_sync_inbox(dry_run: bool = False, lookback_days: int = 3) -> CapabilityCall:
    args = {"dry_run": dry_run, "lookback_days": lookback_days}
    try:
        summary = capabilities.sync_inbox(dry_run=dry_run, lookback_days=lookback_days)
    except Exception as exc:  # noqa: BLE001
        return _failed("sync_inbox", args, exc)
    return {
        "name": "sync_inbox",
        "args": args,
        "result_summary": f"{summary.processed} emails processed, {len(summary.updates)} status updates",
        "ledger_run_id": summary.run_id,
        "status": "ok",
    }
