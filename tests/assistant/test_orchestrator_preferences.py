"""Routing preferences: deterministic reshape of calibration(). Offline."""
import json

from jobai.assistant.orchestrator.preferences import build_routing_preferences, save_routing_preferences
from jobai.core.ledger.db import Ledger
from jobai.core.ledger.feedback import sync_human_outcomes


def page(fp, status, reason=None, source="Automation", pid=None):
    return {"Job Fingerprint": fp, "Status": status, "Reject Reason": reason, "Source": source, "notion_page_id": pid or f"p-{fp}"}


def approve(ledger, fp, band, pri):
    ledger.record_verdict(fingerprint=fp, jd_hash="h", verdict="approved", node="match", rules_sig="s", fit_band=band, priority=pri)


def test_empty_ledger_returns_a_valid_empty_structure():
    ledger = Ledger.memory()
    prefs = build_routing_preferences(ledger)
    assert prefs["rejection_patterns"] == []
    assert prefs["reject_reasons"] == {}
    assert prefs["interaction_prefs"] == {}
    assert "as_of" in prefs


def test_reshapes_a_populated_ledger_matching_calibration():
    ledger = Ledger.memory()
    for fp, band, pri in [("a", "strong", "P1"), ("b", "strong", "P1"), ("c", "strong", "P1"), ("d", "plausible", "P2")]:
        approve(ledger, fp, band, pri)
    approve(ledger, "c", "plausible", "P2")
    sync_human_outcomes(ledger, [page("a", "Applied"), page("b", "Rejected", "too_senior"), page("c", "Discovered"), page("d", "Rejected", "company")])
    sync_human_outcomes(ledger, [page("c", "Shortlisted")])
    prefs = build_routing_preferences(ledger)
    assert prefs["rejection_patterns"] == [
        {"priority": "P1", "positive": 1, "rejected": 1, "undecided": 0, "kept_rate": 0.5},
        {"priority": "P2", "positive": 1, "rejected": 1, "undecided": 0, "kept_rate": 0.5},
    ]
    assert prefs["reject_reasons"] == {"too_senior": 1, "company": 1}
    assert prefs["interaction_prefs"] == {}


def test_kept_rate_is_null_when_there_are_no_decisions_yet():
    ledger = Ledger.memory()
    approve(ledger, "a", "strong", "P1")
    prefs = build_routing_preferences(ledger)
    assert prefs["rejection_patterns"] == [
        {"priority": "P1", "positive": 0, "rejected": 0, "undecided": 1, "kept_rate": None},
    ]


def test_save_routing_preferences_writes_valid_json_that_round_trips(tmp_path):
    ledger = Ledger.memory()
    approve(ledger, "a", "strong", "P1")
    sync_human_outcomes(ledger, [page("a", "Applied")])
    path = tmp_path / "routing_preferences.json"
    written = save_routing_preferences(ledger, path)
    loaded = json.loads(path.read_text())
    written_no_ts = {k: v for k, v in written.items() if k != "as_of"}
    loaded_no_ts = {k: v for k, v in loaded.items() if k != "as_of"}
    assert written_no_ts == loaded_no_ts
    assert "as_of" in loaded
