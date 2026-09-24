import pytest

from src.ledger.conservation import check_conservation
from src.ledger.db import Ledger


def balanced_run(*, write=True):
    """A small, correct run: 10 fetched -> 6 filtered -> 4 dedupe (1 dup) -> 3 triage (1 rejected) -> 2 match (1 weak) -> 1 write."""
    ledger = Ledger.memory()
    run = ledger.start_run("discovery")
    ledger.record_funnel(run, "fetch", {"normalized": 10})
    ledger.record_funnel(run, "stage0", {"stale": 4, "generic_title": 1, "duplicate_in_run": 1, "passed_stage0": 4})
    ev = lambda node, item, disp, code: ledger.record_event(run_id=run, item_id=item, node=node, disposition=disp, reason_code=code)
    for i in "abcd":
        ev("dedupe", i, "passed" if i != "d" else "skipped", "passed_dedupe" if i != "d" else "duplicate_id")
    ev("triage", "a", "passed", "approved_triage")
    ev("triage", "b", "passed", "approved_triage")
    ev("triage", "c", "rejected", "rejected_role_type")
    ev("match", "a", "passed", "approved_match")
    ev("match", "b", "rejected", "rejected_weak")
    if write:
        ev("write", "a", "passed", "written_new")
    return ledger, run, ev


def test_a_balanced_run_has_no_violations():
    ledger, run, _ = balanced_run()
    assert check_conservation(ledger, run) == []


def test_a_silently_dropped_item_is_named():
    ledger, run, _ = balanced_run()
    ledger._conn.execute("DELETE FROM events WHERE item_id='b' AND node='match'")
    (v,) = check_conservation(ledger, run)
    assert "1 item(s) passed triage but have no match event: b" in v


def test_an_item_that_skipped_a_stage_is_caught():
    ledger, run, ev = balanced_run()
    ev("write", "c", "passed", "written_new")  # 'c' was rejected at triage; it must never reach write
    assert any("reached write without passing match: c" in v for v in check_conservation(ledger, run))


def test_stage0_that_loses_items_is_caught_with_the_size_of_the_hole():
    ledger, run, _ = balanced_run()
    ledger._conn.execute("UPDATE funnel SET n = n - 3 WHERE node='stage0' AND reason_code='stale'")
    assert any("stage0 accounted for 7 items but fetch normalized 10 (+3 unaccounted)" in v for v in check_conservation(ledger, run))


def test_dedupe_count_must_match_what_stage0_passed():
    ledger, run, _ = balanced_run()
    ledger._conn.execute("DELETE FROM events WHERE item_id='d' AND node='dedupe'")
    assert any("stage0 passed 4 items but dedupe recorded 3" in v for v in check_conservation(ledger, run))


def test_dry_runs_are_not_expected_to_write():
    ledger, run, _ = balanced_run(write=False)
    assert check_conservation(ledger, run, dry_run=True) == []
    assert any("no write event" in v for v in check_conservation(ledger, run, dry_run=False))


def test_an_empty_run_balances_trivially():
    ledger = Ledger.memory()
    run = ledger.start_run("discovery")
    assert check_conservation(ledger, run) == []


def test_runs_are_audited_independently():
    ledger, run, _ = balanced_run()
    other = ledger.start_run("discovery")
    ledger.record_funnel(other, "fetch", {"normalized": 5})
    assert check_conservation(ledger, run) == []
    assert check_conservation(ledger, other) != []
