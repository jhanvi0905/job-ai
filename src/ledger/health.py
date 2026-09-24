"""Tripwires over the ledger: does the last 24h look healthy?

Phase 1 checks (model calls): spend, guardrails, failure/retry rates, latency,
model-version drift, run outcomes.
Phase 2 checks (item events): conservation (nothing silently lost between
stages), verdict uniformity (a model that says the same thing about everything
is broken even though nothing "failed"), empty evidence (retrieval, not model,
is failing), and runs that started but never finished.

Each check answers a "which layer is failing?" question:
    spend / blocked      -> cost guardrails
    failure_rate         -> provider / transport
    schema_invalid       -> model output layer (prompt or model regression)
    retry_rate / latency -> provider health
    model_drift          -> silent upstream change
    runs / stuck_runs    -> whole-pipeline failures
    conservation         -> silent item loss between stages
    verdicts             -> miscalibration (uniform outputs)
    empty_evidence       -> retrieval / index problems
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.ledger.conservation import check_conservation
from src.ledger.db import Ledger

_ORDER = {"crit": 0, "warn": 1, "ok": 2}
_GUARDRAIL_ROWS = "('budget_exceeded','circuit_open')"


@dataclass(frozen=True)
class Finding:
    level: str  # ok | warn | crit
    name: str
    message: str


def _since(hours: float, now: datetime) -> str:
    return (now - timedelta(hours=hours)).isoformat()


def _p95(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def check(ledger: Ledger, budget: dict, now: datetime | None = None, window_hours: float = 24) -> list[Finding]:
    now = now or datetime.now(timezone.utc)
    since = _since(window_hours, now)
    out: list[Finding] = []

    # --- spend today vs the daily cap -----------------------------------
    spent, cap = ledger.spent_today(), budget.get("per_day_usd", 0.30)
    pct = spent / cap if cap else 0.0
    level = "crit" if pct >= 1 else "warn" if pct >= 0.8 else "ok"
    out.append(Finding(level, "spend", f"${spent:.5f} of ${cap:.2f} daily cap ({pct:.0%})"))

    # --- guardrails that fired ------------------------------------------
    blocked = ledger.query(
        f"SELECT outcome, COUNT(*) AS n FROM llm_calls WHERE created_at >= ? AND outcome IN {_GUARDRAIL_ROWS} GROUP BY outcome",
        (since,),
    )
    if blocked:
        detail = ", ".join(f"{b['outcome']} x{b['n']}" for b in blocked)
        out.append(Finding("crit", "guardrails", f"tripped in last {window_hours:g}h: {detail}"))
    else:
        out.append(Finding("ok", "guardrails", "no budget or circuit-breaker trips"))

    calls = ledger.query(
        f"SELECT outcome, attempt, latency_ms, model_requested, model_resolved FROM llm_calls"
        f" WHERE created_at >= ? AND outcome NOT IN {_GUARDRAIL_ROWS}",
        (since,),
    )
    n = len(calls)
    if n == 0:
        out.append(Finding("ok", "calls", f"no model calls in the last {window_hours:g}h"))
    else:
        bad = [c for c in calls if c["outcome"] != "ok"]
        rate = len(bad) / n
        level = "crit" if rate > 0.20 else "warn" if rate > 0.05 else "ok"
        tops = {}
        for c in bad:
            tops[c["outcome"]] = tops.get(c["outcome"], 0) + 1
        top = ", ".join(f"{k} x{v}" for k, v in sorted(tops.items(), key=lambda kv: -kv[1])[:3]) or "none"
        out.append(Finding(level, "failure_rate", f"{len(bad)}/{n} attempts failed ({rate:.1%}); top: {top}"))

        schema = sum(1 for c in calls if c["outcome"] == "schema_invalid") / n
        level = "crit" if schema > 0.10 else "warn" if schema > 0.02 else "ok"
        out.append(Finding(level, "schema_invalid", f"{schema:.1%} of attempts returned output that failed validation"))

        retried = sum(1 for c in calls if c["attempt"] > 1) / n
        out.append(Finding("warn" if retried > 0.15 else "ok", "retry_rate", f"{retried:.1%} of attempts were retries"))

        lat = [c["latency_ms"] for c in calls if c["latency_ms"] is not None]
        if lat:
            p95 = _p95(lat)
            out.append(Finding("warn" if p95 > 20_000 else "ok", "latency_p95", f"{p95} ms"))

    # --- silent upstream model changes (7 days) -------------------------
    versions = ledger.query(
        "SELECT model_requested, COUNT(DISTINCT model_resolved) AS n, GROUP_CONCAT(DISTINCT model_resolved) AS v"
        " FROM llm_calls WHERE created_at >= ? AND model_resolved IS NOT NULL GROUP BY model_requested",
        (_since(24 * 7, now),),
    )
    drift = [v for v in versions if v["n"] > 1]
    if drift:
        out.append(Finding("warn", "model_drift", "; ".join(f"{d['model_requested']} resolved to {d['v']}" for d in drift)))
    else:
        out.append(Finding("ok", "model_drift", "provider model version stable over 7 days"))

    # --- whole-run outcomes ---------------------------------------------
    runs = ledger.query("SELECT status, COUNT(*) AS n FROM runs WHERE started_at >= ? GROUP BY status", (since,))
    by = {r["status"]: r["n"] for r in runs}
    if by.get("failed"):
        out.append(Finding("crit", "runs", f"{by['failed']} run(s) failed in the last {window_hours:g}h"))
    elif by.get("degraded"):
        out.append(Finding("warn", "runs", f"{by['degraded']} run(s) finished degraded (AI errors; retried next run)"))
    else:
        out.append(Finding("ok", "runs", f"{sum(by.values())} run(s), none failed or degraded"))

    out.extend(_item_level_findings(ledger, now, since, window_hours))
    return sorted(out, key=lambda f: _ORDER[f.level])


def _item_level_findings(ledger: Ledger, now: datetime, since: str, window_hours: float) -> list[Finding]:
    out: list[Finding] = []

    # --- runs that never finished (crash / kill) -------------------------
    stuck = ledger.query(
        "SELECT run_id, graph, started_at FROM runs WHERE status = 'running' AND started_at < ?", (_since(2, now),)
    )
    if stuck:
        out.append(Finding("crit", "stuck_runs", f"{len(stuck)} run(s) started >2h ago and never finished (crashed?): {stuck[0]['run_id']}"))
    else:
        out.append(Finding("ok", "stuck_runs", "no runs left hanging"))

    # --- conservation: nothing may vanish between stages -----------------
    runs = ledger.query(
        "SELECT run_id FROM runs WHERE graph = 'discovery' AND status IN ('ok','degraded') AND started_at >= ?", (since,)
    )
    broken = [(r["run_id"], v[0]) for r in runs if (v := check_conservation(ledger, r["run_id"]))]
    if broken:
        out.append(Finding("crit", "conservation", f"{len(broken)} run(s) lost items. {broken[0][0]}: {broken[0][1]}"))
    elif runs:
        out.append(Finding("ok", "conservation", f"{len(runs)} completed run(s), every item accounted for"))
    else:
        out.append(Finding("ok", "conservation", "no completed discovery runs to audit"))

    # --- uniform verdicts: the failure that produces no error ------------
    flagged, judged = [], 0
    for node in ("triage", "match"):
        rows = ledger.query(
            "SELECT reason_code, COUNT(*) AS n FROM events e JOIN runs r ON r.run_id = e.run_id"
            " WHERE e.node = ? AND r.graph = 'discovery' AND e.created_at >= ? AND e.disposition IN ('passed','rejected')"
            " GROUP BY reason_code",
            (node, since),
        )
        total = sum(r["n"] for r in rows)
        judged += total
        if total >= 20:
            top = max(rows, key=lambda r: r["n"])
            if top["n"] / total >= 0.95:
                flagged.append(f"{node}: {top['n']}/{total} verdicts are '{top['reason_code']}'")
    if flagged:
        out.append(Finding("warn", "verdicts", "nearly uniform — check calibration. " + "; ".join(flagged)))
    else:
        out.append(Finding("ok", "verdicts", f"verdict mix looks varied ({judged} judged)" if judged >= 20 else f"too few verdicts to judge ({judged})"))

    # --- retrieval failing (not the model) --------------------------------
    row = ledger.query(
        "SELECT COUNT(*) AS total, SUM(CASE WHEN context_json LIKE '%\"evidence_ids\": []%' THEN 1 ELSE 0 END) AS empty"
        " FROM llm_calls WHERE node = 'analyse_match' AND outcome = 'ok' AND created_at >= ?",
        (since,),
    )[0]
    total, empty = row["total"] or 0, row["empty"] or 0
    if total >= 10 and empty / total > 0.10:
        out.append(Finding("warn", "empty_evidence", f"{empty}/{total} match calls had NO retrieved evidence — an index/retrieval problem, not a model one"))
    else:
        out.append(Finding("ok", "empty_evidence", f"{empty}/{total} match calls had no evidence" if total else "no match calls in window"))
    return out
