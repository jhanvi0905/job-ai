"""Phase 3b: human outcomes read back from Notion and compared to system verdicts. Offline."""
import pytest

import src.workflows.process_job as pj
from src.ledger.db import Ledger
from src.ledger.feedback import calibration, format_calibration, sync_human_outcomes


def page(fp, status, reason=None, source="Automation", pid=None):
    return {"Job Fingerprint": fp, "Status": status, "Reject Reason": reason, "Source": source, "notion_page_id": pid or f"p-{fp}"}


def approve(ledger, fp, band, pri):
    ledger.record_verdict(fingerprint=fp, jd_hash="h", verdict="approved", node="match", rules_sig="s", fit_band=band, priority=pri)


def test_outcomes_are_a_change_history_not_a_daily_snapshot():
    ledger = Ledger.memory()
    assert sync_human_outcomes(ledger, [page("a", "Discovered")]) == 1
    assert sync_human_outcomes(ledger, [page("a", "Discovered")]) == 0  # unchanged -> no new row
    assert sync_human_outcomes(ledger, [page("a", "Applied")]) == 1
    assert sync_human_outcomes(ledger, [page("a", "Rejected", "location")]) == 1
    rows = ledger.query("SELECT status, reject_reason FROM human_outcomes ORDER BY outcome_id")
    assert [(r["status"], r["reject_reason"]) for r in rows] == [("Discovered", None), ("Applied", None), ("Rejected", "location")]


def test_only_automation_pages_with_a_fingerprint_are_tracked():
    ledger = Ledger.memory()
    pages = [page("a", "Applied"), page("b", "Applied", source="Manual"), page(None, "Applied"), {"Status": "Applied"}]
    assert sync_human_outcomes(ledger, pages) == 1
    assert ledger.query("SELECT fingerprint FROM human_outcomes")[0]["fingerprint"] == "a"


def test_calibration_counts_exactly_and_uses_the_latest_decision():
    ledger = Ledger.memory()
    for fp, band, pri in [("a", "strong", "P1"), ("b", "strong", "P1"), ("c", "strong", "P1"), ("d", "plausible", "P2")]:
        approve(ledger, fp, band, pri)
    approve(ledger, "c", "plausible", "P2")  # re-judged later: newest verdict is the one compared
    sync_human_outcomes(ledger, [page("a", "Applied"), page("b", "Rejected", "too_senior"), page("c", "Discovered"), page("d", "Rejected", "company")])
    sync_human_outcomes(ledger, [page("c", "Interested")])
    c = calibration(ledger)
    assert c["approved"] == 4
    assert c["by_priority"] == {
        "P1": {"positive": 1, "rejected": 1, "undecided": 0},
        "P2": {"positive": 1, "rejected": 1, "undecided": 0},
    }
    assert c["reject_reasons"] == {"too_senior": 1, "company": 1}
    assert c["unknown_reasons"] == []


def test_a_job_with_no_human_status_yet_counts_as_undecided():
    ledger = Ledger.memory()
    approve(ledger, "a", "strong", "P1")
    assert calibration(ledger)["by_priority"] == {"P1": {"positive": 0, "rejected": 0, "undecided": 1}}


def test_system_rejections_never_pollute_the_approval_calibration():
    ledger = Ledger.memory()
    ledger.record_verdict(fingerprint="x", jd_hash="h", verdict="rejected", node="triage", rules_sig="s")
    assert calibration(ledger)["approved"] == 0
    assert "No approved" in format_calibration(calibration(ledger))


def test_unknown_reject_reason_is_surfaced_not_silently_coerced():
    ledger = Ledger.memory()
    approve(ledger, "a", "strong", "P1")
    sync_human_outcomes(ledger, [page("a", "Rejected", "salary lol")])
    c = calibration(ledger)
    assert c["reject_reasons"] == {"salary lol": 1} and c["unknown_reasons"] == ["salary lol"]
    assert "WARNING" in format_calibration(c)


def test_report_text_is_readable():
    ledger = Ledger.memory()
    approve(ledger, "a", "strong", "P1")
    approve(ledger, "b", "strong", "P1")
    sync_human_outcomes(ledger, [page("a", "Applied"), page("b", "Rejected", "location")])
    text = format_calibration(calibration(ledger))
    assert "P1: 1 kept, 1 rejected, 0 undecided (50% kept)" in text and "location x1" in text
