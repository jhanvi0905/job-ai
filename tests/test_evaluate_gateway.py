"""Real evaluate() + real gateway + real ledger, against a scripted provider.
Proves the behaviour that matters when things go wrong, at zero cost."""
import pytest

import src.workflows.process_job as pj
from src.config import load_career_rules
from src.jobs.decisions import DecisionCache
from src.jobs.schemas import NormalizedJob
from src.ledger.db import Ledger
from src.ai.provider import LLMProvider
from src.telemetry.logging import RunSummary
from src.workflows.process_job import Candidate, evaluate
from tests.fakes import FakeResponse, RoutedSession, ok

RULES = load_career_rules()
CLASSIFY = {"role_type": "ai_ml_engineering", "role_family": "RF01", "seniority": "senior", "fit": "strong",
            "hard_blocker": False, "key_requirements": ["LLM systems"], "why": "core role"}
REJECT = {**CLASSIFY, "role_type": "non_engineering", "fit": "no", "why": "marketing"}
STRONG = {"requirements": [{"req": "LLM", "importance": "core", "evidence": "direct", "achievement_ids": ["A05"]}],
          "blocker": False, "reason": "strong"}
WEAK = {"requirements": [{"req": "Rust", "importance": "core", "evidence": "none", "achievement_ids": []}],
        "blocker": False, "reason": "weak"}


def job(name):
    return NormalizedJob(
        external_job_id=name, source="greenhouse", source_company_identifier="acme", company_name="Acme",
        title=f"{name} ML Engineer", location="Remote", workplace_type="Remote", description="Build things.",
        job_url="https://x", job_fingerprint=f"greenhouse:{name}", description_hash=f"h-{name}",
    )


def harness(router, *, cfg_budget=None, breaker=5, workers=6, monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setattr(pj, "AI_WORKERS", workers)
    cfg = {
        "provider": {"name": "fake", "base_url": "https://fake.invalid/v1", "api_key_env": "AIMLAPI_KEY"},
        "gateway": {"max_attempts": 3, "backoff_base_s": 0, "backoff_max_s": 0, "circuit_breaker_failures": breaker},
        "budget": {"per_run_usd": 1.0, "per_day_usd": 10.0, "max_calls_per_run": 100, **(cfg_budget or {})},
    }
    ledger = Ledger.memory()
    run_id = ledger.start_run("test")
    session = RoutedSession(router)
    provider = LLMProvider(ledger, run_id, session=session, sleep=lambda s: None, config=cfg, usage_sink=None)
    return provider, session, ledger, DecisionCache(persist=False)


def which(body):
    text = body["messages"][0]["content"]
    name = next(n for n in ("Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot") if f"{n} ML Engineer" in text)
    return name, "checking ONE job's requirements" in text


def test_mixed_batch_routes_each_job_to_the_right_outcome_and_remembers_only_real_rejections(monkeypatch):
    def router(body):
        name, is_match = which(body)
        if is_match:
            return ok(STRONG if name == "Alpha" else WEAK)
        return ok(REJECT if name == "Bravo" else CLASSIFY)

    provider, session, ledger, decisions = harness(router, monkeypatch=monkeypatch)
    summary = RunSummary()
    cands = [Candidate(job(n), None) for n in ("Alpha", "Bravo", "Charlie")]
    approved = evaluate(cands, decisions, RULES, summary, provider)

    assert [c.job.title for c in approved] == ["Alpha ML Engineer"]
    assert (summary.classified, summary.ai_rejected, summary.deeply_analysed, summary.match_rejected) == (3, 1, 2, 1)
    assert decisions.is_known_rejection("greenhouse:Bravo", "h-Bravo")  # stage 1 reject remembered
    assert decisions.is_known_rejection("greenhouse:Charlie", "h-Charlie")  # stage 3 reject remembered
    assert not decisions.is_known_rejection("greenhouse:Alpha", "h-Alpha")
    assert session.calls == 5 and ledger.calls_in_run(ledger.query("SELECT run_id FROM runs")[0]["run_id"]) == 5
    assert {r["outcome"] for r in ledger.query("SELECT outcome FROM llm_calls")} == {"ok"}


def test_budget_running_out_mid_run_defers_the_rest_and_does_not_poison_the_rejection_memory(monkeypatch):
    # One worker => deterministic order. Cap $0.0003, each call $0.0002:
    # call 1 ok ($0.0002), call 2 ok ($0.0004), every later attempt is blocked BEFORE any HTTP request.
    provider, session, ledger, decisions = harness(
        lambda body: ok(CLASSIFY, cost=0.0002), cfg_budget={"per_run_usd": 0.0003}, workers=1, monkeypatch=monkeypatch
    )
    summary = RunSummary()
    names = ("Alpha", "Bravo", "Charlie", "Delta", "Echo")
    approved = evaluate([Candidate(job(n), None) for n in names], decisions, RULES, summary, provider)

    assert session.calls == 2  # exactly two requests ever left the building
    assert approved == [] and summary.classified == 2 and summary.deeply_analysed == 0
    # 3 jobs blocked at triage + the 2 that passed triage blocked at match = 5 deferred, all attributed to the budget
    assert len(summary.ai_errors) == 5 and all("budget_exceeded" in e for e in summary.ai_errors)
    assert len(ledger.query("SELECT 1 FROM llm_calls WHERE outcome='ok'")) == 2
    assert len(ledger.query("SELECT 1 FROM llm_calls WHERE outcome='budget_exceeded'")) == 5
    # a budget stop is not a verdict: NOTHING may be remembered as rejected, so all 5 are retried next run
    assert summary.ai_rejected == 0 and summary.match_rejected == 0
    assert not any(decisions.is_known_rejection(f"greenhouse:{n}", f"h-{n}") for n in names)


def test_total_provider_outage_trips_the_breaker_instead_of_hammering_the_api(monkeypatch):
    provider, session, ledger, decisions = harness(
        lambda body: FakeResponse(500, text="down"), breaker=2, workers=1, monkeypatch=monkeypatch
    )
    summary = RunSummary()
    cands = [Candidate(job(n), None) for n in ("Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot")]
    approved = evaluate(cands, decisions, RULES, summary, provider)

    assert approved == [] and len(summary.ai_errors) == 6
    assert session.calls == 6  # 2 failed calls x 3 attempts, then the breaker: 4 jobs made ZERO requests
    assert len(ledger.query("SELECT 1 FROM llm_calls WHERE outcome='circuit_open'")) == 4
    assert summary.ai_rejected == 0  # an outage is not a rejection...
    for n in ("Alpha", "Foxtrot"):
        assert not decisions.is_known_rejection(f"greenhouse:{n}", f"h-{n}")  # ...so they are retried next run


def test_a_single_bad_response_does_not_take_down_the_batch(monkeypatch):
    def router(body):
        name, is_match = which(body)
        if name == "Bravo" and not is_match:
            return ok("this is not json")  # always garbage for Bravo
        return ok(STRONG if is_match else CLASSIFY)

    provider, _, ledger, decisions = harness(router, monkeypatch=monkeypatch)
    summary = RunSummary()
    approved = evaluate([Candidate(job(n), None) for n in ("Alpha", "Bravo", "Charlie")], decisions, RULES, summary, provider)
    assert sorted(c.job.title for c in approved) == ["Alpha ML Engineer", "Charlie ML Engineer"]
    assert len(summary.ai_errors) == 1 and "Bravo" in summary.ai_errors[0]
    assert not decisions.is_known_rejection("greenhouse:Bravo", "h-Bravo")
