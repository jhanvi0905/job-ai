"""Phase 3a: the verdict store replaces decisions.jsonl. All offline, no model calls."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

import src.workflows.process_job as pj
from src.jobs.decisions import DecisionCache, import_legacy_decisions
from src.ledger.db import MIGRATIONS, Ledger
from src.telemetry.logging import RunSummary
from src.workflows.process_job import Candidate, evaluate
from tests.test_evaluate_gateway import CLASSIFY, REJECT, STRONG, WEAK, RULES, harness, job, which
from tests.fakes import ok


def test_migration_3_adds_tables_without_touching_earlier_data(tmp_path):
    path = tmp_path / "l.db"
    old = Ledger(path)
    run = old.start_run("discovery")
    old.record_call(run_id=run, node="triage", attempt=1, model_requested="m", outcome="ok", cost_usd=0.01)
    old._conn.execute("DELETE FROM schema_version WHERE version = 3")  # simulate a v2 database
    old._conn.execute("DROP TABLE verdicts")
    old._conn.execute("DROP TABLE human_outcomes")
    old.close()
    new = Ledger(path)
    assert new.schema_version() == max(MIGRATIONS) >= 3
    assert new.spent_in_run(run) == pytest.approx(0.01)
    assert new.query("SELECT COUNT(*) AS n FROM verdicts")[0]["n"] == 0


def test_verdict_table_rejects_unknown_verdicts_and_nodes():
    ledger = Ledger.memory()
    with pytest.raises(sqlite3.IntegrityError):
        ledger.record_verdict(fingerprint="f", jd_hash="h", verdict="maybe", node="triage", rules_sig="s")
    with pytest.raises(sqlite3.IntegrityError):
        ledger.record_verdict(fingerprint="f", jd_hash="h", verdict="rejected", node="write", rules_sig="s")


def test_rejections_survive_a_restart_through_the_ledger(tmp_path):
    path = tmp_path / "l.db"
    ledger = Ledger(path)
    run = ledger.start_run("discovery")
    DecisionCache(ledger, run).record_rejection("f1", "h1", "stage1 no", node="triage", code="rejected_role_type")
    ledger.close()
    again = DecisionCache(Ledger(path))
    assert again.is_known_rejection("f1", "h1")
    assert not again.is_known_rejection("f1", "other-hash")
    row = again.ledger.query("SELECT * FROM verdicts")[0]
    assert (row["node"], row["reason_code"], row["run_id"]) == ("triage", "rejected_role_type", run)


def test_dry_run_cache_reads_memory_but_never_writes_it():
    ledger = Ledger.memory()
    DecisionCache(ledger).record_rejection("f1", "h1", "no")
    dry = DecisionCache(ledger, persist=False)
    assert dry.is_known_rejection("f1", "h1")
    dry.record_rejection("f2", "h2", "no")
    assert len(ledger.query("SELECT 1 FROM verdicts")) == 1


def test_a_rejection_made_under_old_rules_or_too_long_ago_is_ignored():
    ledger = Ledger.memory()
    ledger.record_verdict(fingerprint="f1", jd_hash="h1", verdict="rejected", node="triage", rules_sig="OLD-RULES")
    assert not DecisionCache(ledger).is_known_rejection("f1", "h1")
    ancient = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    cache = DecisionCache(ledger)
    ledger.record_verdict(fingerprint="f2", jd_hash="h2", verdict="rejected", node="triage",
                          rules_sig=cache.signature, created_at=ancient)
    assert not DecisionCache(ledger).is_known_rejection("f2", "h2")


def test_the_latest_verdict_wins_and_an_approval_is_not_a_rejection():
    ledger = Ledger.memory()
    cache = DecisionCache(ledger)
    cache.record_rejection("f1", "h1", "no")
    cache.record_approval("f1", "h1", fit_band="strong", priority="P1")
    assert not cache.is_known_rejection("f1", "h1")
    assert not DecisionCache(ledger).is_known_rejection("f1", "h1")  # same after reload
    last = ledger.query("SELECT verdict, fit_band, priority FROM verdicts ORDER BY verdict_id DESC")[0]
    assert (last["verdict"], last["fit_band"], last["priority"]) == ("approved", "strong", "P1")


def test_legacy_import_is_idempotent_and_keeps_original_signature_and_time(tmp_path):
    ledger = Ledger.memory()
    sig = DecisionCache(ledger).signature
    ts = datetime.now(timezone.utc).isoformat()
    legacy = tmp_path / "decisions.jsonl"
    legacy.write_text(
        json.dumps({"fp": "f1", "jd_hash": "h1", "verdict": "rejected", "reason": "stage1 x", "sig": sig, "ts": ts}) + "\n"
        + "not json\n"
        + json.dumps({"fp": "f2", "jd_hash": "h2", "verdict": "rejected", "reason": "old", "sig": "stale", "ts": ts}) + "\n"
    )
    assert import_legacy_decisions(ledger, legacy) == 2
    assert import_legacy_decisions(ledger, legacy) == 0
    assert import_legacy_decisions(ledger, tmp_path / "missing.jsonl") == 0
    cache = DecisionCache(ledger)
    assert cache.is_known_rejection("f1", "h1")      # still valid: keeps saving tokens
    assert not cache.is_known_rejection("f2", "h2")  # rules changed since: re-judged
    assert ledger.query("SELECT created_at FROM verdicts WHERE fingerprint='f1'")[0]["created_at"] == ts


def test_evaluate_persists_every_verdict_with_node_code_and_band(monkeypatch):
    def router(body):
        name, is_match = which(body)
        if is_match:
            return ok(STRONG if name == "Alpha" else WEAK)
        return ok(REJECT if name == "Bravo" else CLASSIFY)

    provider, _, ledger, _ = harness(router, monkeypatch=monkeypatch)
    run = ledger.query("SELECT run_id FROM runs")[0]["run_id"]
    cache = DecisionCache(ledger, run)
    evaluate([Candidate(job(n), None) for n in ("Alpha", "Bravo", "Charlie")], cache, RULES, RunSummary(), provider)
    rows = {r["fingerprint"]: r for r in ledger.query("SELECT * FROM verdicts")}
    assert set(rows) == {"greenhouse:Alpha", "greenhouse:Bravo", "greenhouse:Charlie"}
    assert (rows["greenhouse:Alpha"]["verdict"], rows["greenhouse:Alpha"]["node"]) == ("approved", "match")
    assert rows["greenhouse:Alpha"]["fit_band"] and rows["greenhouse:Alpha"]["priority"] in ("P1", "P2")
    assert (rows["greenhouse:Bravo"]["verdict"], rows["greenhouse:Bravo"]["node"], rows["greenhouse:Bravo"]["reason_code"]) == ("rejected", "triage", "rejected_role_type")
    assert (rows["greenhouse:Charlie"]["node"], rows["greenhouse:Charlie"]["reason_code"]) == ("match", "rejected_weak")
