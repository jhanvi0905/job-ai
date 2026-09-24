from datetime import datetime, timedelta, timezone

from src.ledger.db import Ledger
from src.ledger.health import check

BUDGET = {"per_day_usd": 0.30}


def add(ledger, run_id, n=1, *, outcome="ok", cost=0.0001, attempt=1, latency=500, resolved="gpt-4o-mini-2024-07-18",
        model="gpt-4o-mini", age_hours=0.0):
    ts = (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat()
    for _ in range(n):
        ledger._conn.execute(
            "INSERT INTO llm_calls (run_id,node,attempt,model_requested,model_resolved,outcome,cost_usd,latency_ms,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, "triage", attempt, model, resolved, outcome, cost, latency, ts),
        )


def by_name(findings):
    return {f.name: f for f in findings}


def fresh():
    ledger = Ledger.memory()
    return ledger, ledger.start_run("discovery")


def test_a_healthy_ledger_has_no_warnings():
    ledger, run = fresh()
    add(ledger, run, 40)
    ledger.finish_run(run, "ok")
    assert {f.level for f in check(ledger, BUDGET)} == {"ok"}


def test_empty_ledger_is_ok_not_an_error():
    f = by_name(check(Ledger.memory(), BUDGET))
    assert f["calls"].level == "ok" and f["spend"].level == "ok"


def test_spend_warns_at_80_percent_and_is_critical_at_the_cap():
    ledger, run = fresh()
    add(ledger, run, 1, cost=0.25)
    assert by_name(check(ledger, BUDGET))["spend"].level == "warn"
    add(ledger, run, 1, cost=0.10)
    assert by_name(check(ledger, BUDGET))["spend"].level == "crit"


def test_failure_rate_thresholds_and_top_causes():
    ledger, run = fresh()
    add(ledger, run, 90)
    add(ledger, run, 6, outcome="http_429")
    f = by_name(check(ledger, BUDGET))["failure_rate"]
    assert f.level == "warn" and "http_429 x6" in f.message
    add(ledger, run, 30, outcome="http_5xx")
    assert by_name(check(ledger, BUDGET))["failure_rate"].level == "crit"


def test_schema_invalid_is_reported_as_a_model_layer_problem():
    ledger, run = fresh()
    add(ledger, run, 90)
    add(ledger, run, 5, outcome="schema_invalid")
    assert by_name(check(ledger, BUDGET))["schema_invalid"].level == "warn"


def test_a_tripped_guardrail_is_always_critical():
    ledger, run = fresh()
    add(ledger, run, 5)
    add(ledger, run, 1, outcome="budget_exceeded", cost=0)
    f = by_name(check(ledger, BUDGET))["guardrails"]
    assert f.level == "crit" and "budget_exceeded x1" in f.message


def test_guardrail_rows_do_not_pollute_the_failure_rate():
    ledger, run = fresh()
    add(ledger, run, 10)
    add(ledger, run, 50, outcome="circuit_open", cost=0)
    assert by_name(check(ledger, BUDGET))["failure_rate"].level == "ok"


def test_retry_heavy_and_slow_providers_warn():
    ledger, run = fresh()
    add(ledger, run, 10, attempt=2, latency=30_000)
    f = by_name(check(ledger, BUDGET))
    assert f["retry_rate"].level == "warn" and f["latency_p95"].level == "warn"


def test_model_version_drift_is_detected_across_a_week():
    ledger, run = fresh()
    add(ledger, run, 5, resolved="gpt-4o-mini-2024-07-18", age_hours=24 * 5)
    add(ledger, run, 5, resolved="gpt-4o-mini-2025-01-01")
    f = by_name(check(ledger, BUDGET))["model_drift"]
    assert f.level == "warn" and "gpt-4o-mini-2025-01-01" in f.message


def test_failed_and_degraded_runs_are_surfaced():
    ledger, run = fresh()
    ledger.finish_run(run, "degraded")
    assert by_name(check(ledger, BUDGET))["runs"].level == "warn"
    bad = ledger.start_run("discovery")
    ledger.finish_run(bad, "failed", "boom")
    assert by_name(check(ledger, BUDGET))["runs"].level == "crit"


def test_old_problems_outside_the_window_are_ignored():
    ledger, run = fresh()
    add(ledger, run, 50, outcome="http_5xx", age_hours=48)
    add(ledger, run, 10)
    assert by_name(check(ledger, BUDGET))["failure_rate"].level == "ok"


def test_findings_are_sorted_worst_first():
    ledger, run = fresh()
    add(ledger, run, 5)
    add(ledger, run, 1, outcome="circuit_open", cost=0)
    levels = [f.level for f in check(ledger, BUDGET)]
    assert levels == sorted(levels, key={"crit": 0, "warn": 1, "ok": 2}.get)


# ---------------------------------------------------------------- Phase 2 checks
from tests.test_conservation import balanced_run  # noqa: E402


def ev(ledger, run, node, item, disposition, code):
    ledger.record_event(run_id=run, item_id=item, node=node, disposition=disposition, reason_code=code)


def test_a_balanced_completed_run_passes_the_conservation_audit():
    ledger, run, _ = balanced_run()
    ledger.finish_run(run, "ok")
    assert by_name(check(ledger, BUDGET))["conservation"].level == "ok"


def test_a_run_that_lost_an_item_is_critical_and_names_it():
    ledger, run, _ = balanced_run()
    ledger._conn.execute("DELETE FROM events WHERE item_id='b' AND node='match'")
    ledger.finish_run(run, "ok")
    f = by_name(check(ledger, BUDGET))["conservation"]
    assert f.level == "crit" and "no match event: b" in f.message


def test_runs_still_in_flight_and_other_graphs_are_not_audited():
    ledger, run, _ = balanced_run()
    ledger._conn.execute("DELETE FROM events WHERE item_id='b' AND node='match'")
    assert by_name(check(ledger, BUDGET))["conservation"].level == "ok"  # still 'running'
    ledger.finish_run(run, "ok")
    ledger._conn.execute("UPDATE runs SET graph='discovery-dry' WHERE run_id=?", (run,))
    assert by_name(check(ledger, BUDGET))["conservation"].level == "ok"


def _verdicts(ledger, run, node, code, n, disposition="rejected", prefix="i"):
    for i in range(n):
        ev(ledger, run, node, f"{prefix}{node}{code}{i}", disposition, code)


def test_uniform_verdicts_are_flagged_even_though_nothing_failed():
    """The '35 of 35 weak' incident: no error, no log line, completely wrong."""
    ledger, run = fresh()
    _verdicts(ledger, run, "match", "rejected_weak", 35)
    f = by_name(check(ledger, BUDGET))["verdicts"]
    assert f.level == "warn" and "35/35" in f.message and "rejected_weak" in f.message


def test_a_varied_verdict_mix_is_fine_and_small_samples_are_not_judged():
    ledger, run = fresh()
    _verdicts(ledger, run, "match", "rejected_weak", 12)
    _verdicts(ledger, run, "match", "approved_match", 10, disposition="passed")
    assert by_name(check(ledger, BUDGET))["verdicts"].level == "ok"
    other, r2 = fresh()
    _verdicts(other, r2, "match", "rejected_weak", 19)
    f = by_name(check(other, BUDGET))["verdicts"]
    assert f.level == "ok" and "too few" in f.message


def test_deferred_and_errored_items_do_not_count_as_verdicts():
    ledger, run = fresh()
    _verdicts(ledger, run, "triage", "llm_budget", 30, disposition="deferred")
    assert "too few" in by_name(check(ledger, BUDGET))["verdicts"].message


def test_empty_retrieval_is_reported_as_a_retrieval_problem():
    ledger, run = fresh()
    for i in range(10):
        ledger.record_call(run_id=run, node="analyse_match", attempt=1, model_requested="m", outcome="ok",
                           context={"evidence_ids": [] if i < 3 else ["A01"]})
    f = by_name(check(ledger, BUDGET))["empty_evidence"]
    assert f.level == "warn" and "3/10" in f.message and "retrieval" in f.message


def test_healthy_retrieval_and_tiny_samples_are_fine():
    ledger, run = fresh()
    for i in range(10):
        ledger.record_call(run_id=run, node="analyse_match", attempt=1, model_requested="m", outcome="ok", context={"evidence_ids": ["A01"]})
    assert by_name(check(ledger, BUDGET))["empty_evidence"].level == "ok"


def test_a_run_that_started_and_never_finished_is_critical():
    ledger, run = fresh()
    long_ago = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    ledger._conn.execute("UPDATE runs SET started_at=? WHERE run_id=?", (long_ago, run))
    f = by_name(check(ledger, BUDGET))["stuck_runs"]
    assert f.level == "crit" and run in f.message


def test_a_run_that_is_merely_in_progress_is_not_stuck():
    ledger, run = fresh()
    assert by_name(check(ledger, BUDGET))["stuck_runs"].level == "ok"
