import sqlite3

import pytest

from jobai.core.ledger.codes import DISPOSITIONS, NODE_REASONS, REASON_CODES
from jobai.core.ledger.db import MIGRATIONS, Ledger
from jobai.core.ledger.events import NULL_EVENTS, Events


def fresh():
    ledger = Ledger.memory()
    return ledger, ledger.start_run("discovery")


def test_migration_2_adds_event_tables_without_touching_phase_1_data(tmp_path):
    path = tmp_path / "l.db"
    old = Ledger(path)
    run = old.start_run("discovery")
    old.record_call(run_id=run, node="triage", attempt=1, model_requested="m", outcome="ok", cost_usd=0.01)
    old.close()
    new = Ledger(path)
    assert new.schema_version() == max(MIGRATIONS)
    assert new.spent_in_run(run) == pytest.approx(0.01)
    assert {"events", "funnel"} <= {r["name"] for r in new.query("SELECT name FROM sqlite_master WHERE type='table'")}


def test_an_event_round_trips():
    ledger, run = fresh()
    ledger.record_event(run_id=run, item_id="gh:1", node="triage", disposition="rejected",
                        reason_code="rejected_role_type", detail="marketing role")
    (row,) = ledger.query("SELECT * FROM events")
    assert (row["node"], row["disposition"], row["reason_code"], row["detail"]) == (
        "triage", "rejected", "rejected_role_type", "marketing role")


def test_a_second_terminal_event_for_the_same_item_and_node_is_refused():
    ledger, run = fresh()
    kw = dict(run_id=run, item_id="gh:1", node="triage", disposition="passed", reason_code="approved_triage")
    ledger.record_event(**kw)
    with pytest.raises(sqlite3.IntegrityError):
        ledger.record_event(**kw)


def test_the_same_item_may_have_one_event_per_node_and_per_run():
    ledger, run = fresh()
    other = ledger.start_run("discovery")
    for r in (run, other):
        for node, code in (("dedupe", "passed_dedupe"), ("triage", "approved_triage")):
            ledger.record_event(run_id=r, item_id="gh:1", node=node, disposition="passed", reason_code=code)
    assert len(ledger.query("SELECT 1 FROM events")) == 4


def test_a_reason_code_from_the_wrong_node_is_rejected():
    ledger, run = fresh()
    with pytest.raises(ValueError):
        ledger.record_event(run_id=run, item_id="x", node="write", disposition="passed", reason_code="stale")
    with pytest.raises(ValueError):
        ledger.record_event(run_id=run, item_id="x", node="nowhere", disposition="passed", reason_code="stale")


def test_the_database_itself_rejects_unknown_dispositions():
    ledger, run = fresh()
    with pytest.raises(sqlite3.IntegrityError):
        ledger.record_event(run_id=run, item_id="x", node="triage", disposition="vanished", reason_code="approved_triage")


def test_funnel_counts_accumulate_and_zero_counts_are_not_stored():
    ledger, run = fresh()
    ledger.record_funnel(run, "stage0", {"stale": 100, "generic_title": 50, "passed_stage0": 0})
    ledger.record_funnel(run, "stage0", {"stale": 5})
    rows = {r["reason_code"]: r["n"] for r in ledger.query("SELECT * FROM funnel")}
    assert rows == {"stale": 105, "generic_title": 50}


def test_funnel_rejects_codes_that_do_not_belong_to_the_node():
    ledger, run = fresh()
    with pytest.raises(ValueError):
        ledger.record_funnel(run, "stage0", {"written_new": 1})


def test_every_reason_code_belongs_to_at_least_one_node_and_dispositions_are_closed():
    assert REASON_CODES == frozenset().union(*NODE_REASONS.values())
    assert DISPOSITIONS == {"passed", "rejected", "skipped", "deferred", "errored"}


def test_strict_events_raise_on_bugs():
    ledger, run = fresh()
    events = Events(ledger, run, strict=True)
    events.item("triage", "gh:1", "passed", "approved_triage")
    with pytest.raises(sqlite3.IntegrityError):
        events.item("triage", "gh:1", "passed", "approved_triage")
    with pytest.raises(ValueError):
        events.item("triage", "gh:2", "passed", "stale")


def test_lenient_events_never_break_a_run_but_count_the_damage():
    ledger, run = fresh()
    events = Events(ledger, run, strict=False)
    events.item("triage", "gh:1", "passed", "approved_triage")
    events.item("triage", "gh:1", "passed", "approved_triage")  # duplicate
    events.item("triage", "gh:2", "passed", "stale")  # wrong code
    assert events.write_failures == 2
    assert len(ledger.query("SELECT 1 FROM events")) == 1


def test_null_events_accept_everything_and_record_nothing():
    NULL_EVENTS.item("triage", "x", "passed", "anything-at-all")
    NULL_EVENTS.funnel("stage0", {"whatever": 1})
    assert NULL_EVENTS.write_failures == 0
