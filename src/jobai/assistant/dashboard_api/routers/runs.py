"""Ledger-backed run history, health tripwires, calibration, and manual
triggers for the two writable graphs (discover_jobs, sync_inbox).

discover_jobs/sync_inbox are imported by name (not behind a dict built at
import time) so `patch("jobai.assistant.dashboard_api.routers.runs.discover_jobs", ...)`
in tests actually takes effect — the trigger endpoints look the names up in
this module's globals at call time.

get_ledger() is a factory (not a hardcoded `Ledger()` call in each handler)
so tests can monkeypatch it to hand back a single shared in-memory/tmp Ledger
across a whole test.
"""
from __future__ import annotations

import dataclasses
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from jobai.assistant.capabilities import discover_jobs, sync_inbox
from jobai.core.config import load_models, load_yaml
from jobai.core.ledger.conservation import check_conservation
from jobai.core.ledger.db import Ledger
from jobai.core.ledger.feedback import calibration as _calibration
from jobai.core.ledger.feedback import format_calibration
from jobai.core.ledger.health import check as _check_health

router = APIRouter()

_RUN_COLUMNS = "run_id, graph, started_at, ended_at, status, budget_usd, note"

_ledger_singleton: Ledger | None = None


def get_ledger() -> Ledger:
    global _ledger_singleton
    if _ledger_singleton is None:
        _ledger_singleton = Ledger()
    return _ledger_singleton


class TriggerRequest(BaseModel):
    graph: Literal["discover_jobs", "sync_inbox"]


class ConfirmTriggerRequest(TriggerRequest):
    confirm: bool = False


def _run_graph(graph: str, *, dry_run: bool):
    if graph == "discover_jobs":
        return discover_jobs(dry_run=dry_run)
    return sync_inbox(dry_run=dry_run)


@router.get("/runs")
def list_runs(limit: int = 20) -> list[dict]:
    ledger = get_ledger()
    return ledger.query(f"SELECT {_RUN_COLUMNS} FROM runs ORDER BY started_at DESC LIMIT ?", (limit,))


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    ledger = get_ledger()
    rows = ledger.query(f"SELECT {_RUN_COLUMNS} FROM runs WHERE run_id = ?", (run_id,))
    if not rows:
        raise HTTPException(status_code=404, detail=f"no such run: {run_id!r}")
    funnel = ledger.query("SELECT * FROM funnel WHERE run_id = ?", (run_id,))
    llm_calls = ledger.query("SELECT * FROM llm_calls WHERE run_id = ?", (run_id,))
    violations = check_conservation(ledger, run_id)
    return {**rows[0], "funnel": funnel, "llm_calls": llm_calls, "conservation_ok": not violations}


@router.get("/health")
def health() -> list[dict]:
    ledger = get_ledger()
    findings = _check_health(ledger, load_models().get("budget", {}))
    return [{"level": f.level, "name": f.name, "message": f.message} for f in findings]


@router.get("/calibration")
def calibration() -> dict:
    ledger = get_ledger()
    result = _calibration(ledger)
    return {**result, "text": format_calibration(result)}


@router.post("/runs/trigger/preview")
def trigger_preview(body: TriggerRequest) -> dict:
    load_yaml.cache_clear()  # reflect any config edit saved just before this call
    try:
        summary = _run_graph(body.graph, dry_run=True)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "dry_run": True, "summary": dataclasses.asdict(summary)}


@router.post("/runs/trigger/confirm")
def trigger_confirm(body: ConfirmTriggerRequest) -> dict:
    if body.confirm is not True:
        raise HTTPException(status_code=400, detail="confirm must be true")
    load_yaml.cache_clear()
    try:
        summary = _run_graph(body.graph, dry_run=False)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"ok": True, "dry_run": False, "summary": dataclasses.asdict(summary)}
