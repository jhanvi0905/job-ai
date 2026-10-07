import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from jobai.core.ledger.codes import CALL_OUTCOMES
from jobai.core.ledger.db import MIGRATIONS, Ledger


def call(ledger, run_id, **o):
    d = dict(run_id=run_id, node="triage", attempt=1, model_requested="m", outcome="ok", cost_usd=0.001)
    d.update(o)
    ledger.record_call(**d)


def test_schema_is_created_and_versioned():
    ledger = Ledger.memory()
    assert ledger.schema_version() == max(MIGRATIONS)
    tables = {r["name"] for r in ledger.query("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"runs", "llm_calls", "schema_version"} <= tables


def test_reopening_an_existing_database_does_not_remigrate(tmp_path):
    path = tmp_path / "ledger.db"
    first = Ledger(path)
    run_id = first.start_run("discovery")
    first.close()
    second = Ledger(path)
    assert second.schema_version() == max(MIGRATIONS)
    assert second.query("SELECT run_id FROM runs")[0]["run_id"] == run_id


def test_unknown_outcome_is_rejected_by_the_database_itself():
    ledger = Ledger.memory()
    run_id = ledger.start_run("discovery")
    with pytest.raises(sqlite3.IntegrityError):
        call(ledger, run_id, outcome="something_new")


def test_every_declared_outcome_is_accepted():
    ledger = Ledger.memory()
    run_id = ledger.start_run("discovery")
    for outcome in CALL_OUTCOMES:
        call(ledger, run_id, outcome=outcome)
    assert len(ledger.query("SELECT 1 FROM llm_calls")) == len(CALL_OUTCOMES)


def test_calls_must_belong_to_a_real_run():
    ledger = Ledger.memory()
    with pytest.raises(sqlite3.IntegrityError):
        call(ledger, "no-such-run")


def test_negative_cost_and_zero_attempt_are_rejected():
    ledger = Ledger.memory()
    run_id = ledger.start_run("discovery")
    with pytest.raises(sqlite3.IntegrityError):
        call(ledger, run_id, cost_usd=-1)
    with pytest.raises(sqlite3.IntegrityError):
        call(ledger, run_id, attempt=0)


def test_spend_and_call_counts_per_run_are_isolated():
    ledger = Ledger.memory()
    a, b = ledger.start_run("discovery"), ledger.start_run("discovery")
    call(ledger, a, cost_usd=0.002)
    call(ledger, a, cost_usd=0.003)
    call(ledger, b, cost_usd=0.010)
    assert ledger.spent_in_run(a) == pytest.approx(0.005)
    assert ledger.spent_in_run(b) == pytest.approx(0.010)
    assert ledger.calls_in_run(a) == 2


def test_guardrail_rows_are_not_counted_as_real_calls():
    ledger = Ledger.memory()
    run_id = ledger.start_run("discovery")
    call(ledger, run_id, outcome="ok")
    call(ledger, run_id, outcome="budget_exceeded", cost_usd=0)
    call(ledger, run_id, outcome="circuit_open", cost_usd=0)
    assert ledger.calls_in_run(run_id) == 1


def test_spent_today_excludes_yesterday():
    ledger = Ledger.memory()
    run_id = ledger.start_run("discovery")
    call(ledger, run_id, cost_usd=0.01)
    yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    ledger._conn.execute(
        "INSERT INTO llm_calls (run_id,node,attempt,model_requested,outcome,cost_usd,created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (run_id, "triage", 1, "m", "ok", 5.0, yesterday),
    )
    assert ledger.spent_today() == pytest.approx(0.01)


def test_run_lifecycle_and_final_status_validation():
    ledger = Ledger.memory()
    run_id = ledger.start_run("discovery", budget_usd=0.15, code_version="abc", config_signature="sig")
    assert ledger.query("SELECT status FROM runs")[0]["status"] == "running"
    ledger.finish_run(run_id, "degraded", note="budget hit")
    row = ledger.query("SELECT * FROM runs")[0]
    assert row["status"] == "degraded" and row["ended_at"] and row["note"] == "budget hit"
    with pytest.raises(ValueError):
        ledger.finish_run(run_id, "running")
    with pytest.raises(ValueError):
        ledger.finish_run(run_id, "bogus")


def test_context_is_stored_as_json_and_detail_is_truncated():
    ledger = Ledger.memory()
    run_id = ledger.start_run("discovery")
    call(ledger, run_id, context={"jd_chars": 3900, "jd_truncated": True}, detail="x" * 1000)
    row = ledger.query("SELECT context_json, detail FROM llm_calls")[0]
    assert '"jd_chars": 3900' in row["context_json"]
    assert len(row["detail"]) == 300


def test_concurrent_writers_do_not_corrupt_or_lose_rows(tmp_path):
    """The gateway is used from a thread pool (6 workers)."""
    ledger = Ledger(tmp_path / "ledger.db")
    run_id = ledger.start_run("discovery")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: call(ledger, run_id, item_id=f"job-{i}", cost_usd=0.001), range(200)))
    assert ledger.calls_in_run(run_id) == 200
    assert ledger.spent_in_run(run_id) == pytest.approx(0.2)
