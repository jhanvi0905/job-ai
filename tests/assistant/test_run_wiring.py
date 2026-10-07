"""run() must always go through a ledgered, budgeted provider. Everything external is faked."""
from datetime import UTC

import pytest

import jobai.assistant.workflows.process_job as pj
from jobai.core.ledger.db import Ledger

PAGES: list[dict] = []


class FakeNotion:
    def list_all_pages(self):
        return list(PAGES)


@pytest.fixture
def wired(monkeypatch):
    seen = {}
    PAGES.clear()
    monkeypatch.setattr(pj, "NotionClient", FakeNotion)
    monkeypatch.setattr(pj, "build_sources", lambda: [])
    monkeypatch.setattr(pj, "fetch_all", lambda sources, summary: [])
    monkeypatch.setattr(pj, "write_to_notion", lambda *a, **k: seen.setdefault("wrote", True))

    def install(evaluate):
        def wrapper(candidates, decisions, rules, summary, provider, events=None):
            seen["provider"] = provider
            return evaluate(summary)

        monkeypatch.setattr(pj, "evaluate", wrapper)

    seen["install"] = install
    return seen


def last_run():
    ledger = Ledger()
    row = ledger.query("SELECT * FROM runs ORDER BY started_at DESC")[0]
    ledger.close()
    return row


def test_run_opens_a_ledger_run_and_gives_evaluate_a_budgeted_provider(wired):
    wired["install"](lambda summary: [])
    pj.run()
    row = last_run()
    assert row["status"] == "ok" and row["graph"] == "discovery" and row["ended_at"]
    assert row["budget_usd"] == 0.15 and row["config_signature"] and row["code_version"]
    assert wired["provider"].ledger is not None and wired["provider"].run_id == row["run_id"]


def test_ai_errors_mark_the_run_degraded_not_ok(wired):
    wired["install"](lambda summary: summary.ai_errors.append("classify x: budget_exceeded") or [])
    pj.run()
    row = last_run()
    assert row["status"] == "degraded" and "1 AI error" in row["note"]


def test_a_crash_is_recorded_as_failed_and_still_raised(wired):
    def boom(summary):
        raise RuntimeError("kaboom")

    wired["install"](boom)
    with pytest.raises(RuntimeError):
        pj.run()
    row = last_run()
    assert row["status"] == "failed" and "kaboom" in row["note"] and row["ended_at"]


def test_dry_run_is_labelled_and_never_writes_to_notion(wired):
    wired["install"](lambda summary: [])
    pj.run(dry_run=True)
    assert last_run()["graph"] == "discovery-dry"
    assert "wrote" not in wired


def test_no_pipeline_function_will_build_its_own_unbudgeted_provider():
    """Guards the loophole: provider is a required argument everywhere it is used."""
    import inspect

    from jobai.engine.ai.classifier import classify_job
    from jobai.engine.ai.matcher import analyse_match

    for fn in (classify_job, analyse_match, pj.evaluate):
        param = inspect.signature(fn).parameters["provider"]
        assert param.default is inspect.Parameter.empty, f"{fn.__name__} must not default its provider"


def outcomes():
    ledger = Ledger()
    rows = ledger.query("SELECT fingerprint, status FROM human_outcomes")
    ledger.close()
    return rows


def test_a_live_run_captures_your_notion_decisions_for_free(wired):
    PAGES.append({"Job Fingerprint": "greenhouse:1", "Status": "Applied", "Source": "Automation", "notion_page_id": "p1"})
    wired["install"](lambda summary: [])
    pj.run()
    assert outcomes() == [{"fingerprint": "greenhouse:1", "status": "Applied"}]


def test_a_dry_run_records_no_human_outcomes(wired):
    PAGES.append({"Job Fingerprint": "greenhouse:1", "Status": "Applied", "Source": "Automation", "notion_page_id": "p1"})
    wired["install"](lambda summary: [])
    pj.run(dry_run=True)
    assert outcomes() == []


def test_feedback_capture_failing_never_fails_the_discovery_run(wired, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("ledger locked")

    monkeypatch.setattr(pj, "sync_human_outcomes", boom)
    wired["install"](lambda summary: [])
    pj.run()
    assert last_run()["status"] == "ok"


def test_legacy_rejections_are_imported_into_the_ledger_on_the_first_run(wired, tmp_path, monkeypatch):
    import json
    from datetime import datetime

    legacy = tmp_path / "decisions.jsonl"
    legacy.write_text(json.dumps({"fp": "f1", "jd_hash": "h1", "verdict": "rejected", "reason": "r", "sig": "s",
                                  "ts": datetime.now(UTC).isoformat()}) + "\n")
    monkeypatch.setattr("jobai.engine.jobs.decisions.LEGACY_DECISIONS_PATH", legacy)
    wired["install"](lambda summary: [])
    pj.run()
    pj.run()
    ledger = Ledger()
    assert ledger.query("SELECT COUNT(*) AS n FROM verdicts WHERE node='legacy'")[0]["n"] == 1
    ledger.close()
