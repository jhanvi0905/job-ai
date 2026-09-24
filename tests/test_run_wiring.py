"""run() must always go through a ledgered, budgeted provider. Everything external is faked."""
import pytest

import src.workflows.process_job as pj
from src.ledger.db import Ledger


class FakeNotion:
    def list_all_pages(self):
        return []


@pytest.fixture
def wired(monkeypatch):
    seen = {}
    monkeypatch.setattr(pj, "NotionClient", FakeNotion)
    monkeypatch.setattr(pj, "build_sources", lambda: [])
    monkeypatch.setattr(pj, "fetch_all", lambda sources, summary: [])
    monkeypatch.setattr(pj, "write_to_notion", lambda *a, **k: seen.setdefault("wrote", True))

    def install(evaluate):
        def wrapper(candidates, decisions, rules, summary, provider):
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

    from src.ai.classifier import classify_job
    from src.ai.matcher import analyse_match

    for fn in (classify_job, analyse_match, pj.evaluate):
        param = inspect.signature(fn).parameters["provider"]
        assert param.default is inspect.Parameter.empty, f"{fn.__name__} must not default its provider"
