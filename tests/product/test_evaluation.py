import pytest
from sqlalchemy import select

from jobai.engine.ai.provider import BudgetExceeded, CircuitOpen
from jobai.product.db.models import SearchPrefs, UsageCounter, UserJobEvaluation
from jobai.product.services import quota
from jobai.product.services.evaluation import DISPOSITIONS, deep_match_job, evaluate_for_user
from jobai.product.services.quota import QuotaExceeded
from tests.product.conftest import (
    BUDGET_ERROR,
    CLASSIFY_NO,
    CLASSIFY_OK,
    MATCH_STRONG,
    MATCH_WEAK,
    FakeProvider,
)


def evals(session, user_id):
    return {e.job_id: e for e in session.scalars(select(UserJobEvaluation).where(UserJobEvaluation.user_id == user_id))}


def test_funnel_conservation_and_dispositions(session, make_user, make_job):
    user = make_user("a@x.com")
    passing = make_job()
    filtered = make_job(title="Account Executive")
    onsite = make_job(location="Berlin", workplace="On-site")
    summary = evaluate_for_user(session, user.id, FakeProvider())
    assert summary.conserved and summary.considered == 3
    rows = evals(session, user.id)
    assert rows[passing.id].disposition == "matched" and rows[passing.id].fit == "strong" and rows[passing.id].fit_rank == 3
    assert rows[filtered.id].disposition == "filtered" and rows[onsite.id].disposition == "filtered"
    assert rows[filtered.id].fit_rank == 0
    assert all(r.disposition in DISPOSITIONS for r in rows.values())
    assert (summary.matched, summary.filtered) == (1, 2)


def test_triage_rejection_and_weak_match(session, make_user, make_job):
    user = make_user("a@x.com")
    make_job()
    summary = evaluate_for_user(session, user.id, FakeProvider(classify=CLASSIFY_NO))
    assert summary.rejected == 1 and summary.conserved
    session.query(UserJobEvaluation).delete(); session.commit()
    summary = evaluate_for_user(session, user.id, FakeProvider(match=MATCH_WEAK))
    row = next(iter(evals(session, user.id).values()))
    assert row.disposition == "rejected" and row.reason_code == "rejected_weak" and row.match


def test_final_fit_is_lower_of_stages(session, make_user, make_job):
    user = make_user("a@x.com")
    make_job()
    evaluate_for_user(session, user.id, FakeProvider(classify={**CLASSIFY_OK, "fit": "plausible"}))
    row = next(iter(evals(session, user.id).values()))
    assert (row.disposition, row.fit, row.fit_rank) == ("matched", "plausible", 2)


def test_cache_hit_costs_zero_llm_calls(session, make_user, make_job):
    user = make_user("a@x.com")
    make_job(); make_job(title="Account Executive")
    first = FakeProvider()
    evaluate_for_user(session, user.id, first)
    assert first.total_calls == 2
    second = FakeProvider()
    summary = evaluate_for_user(session, user.id, second)
    assert second.total_calls == 0 and summary.cached == 2 and summary.conserved
    assert quota.used_today(session, user.id, "triage") == 1


def test_changed_description_or_rules_invalidate_cache(session, make_user, make_job):
    user = make_user("a@x.com")
    job = make_job()
    evaluate_for_user(session, user.id, FakeProvider())
    job.description, job.description_hash = "New text about LLMs.", "newhash"
    session.commit()
    p = FakeProvider()
    evaluate_for_user(session, user.id, p)
    assert p.calls["classify_job"] == 1
    session.add(SearchPrefs(user_id=user.id, data={"total_years": 7})); session.commit()
    p = FakeProvider()
    evaluate_for_user(session, user.id, p)
    assert p.calls["classify_job"] == 1  # new rules_sig -> re-evaluated


def test_triage_quota_exhaustion_defers_never_rejects(session, make_user, make_job):
    user = make_user("a@x.com", plan="free")  # 40 triage/day
    session.add(UsageCounter(user_id=user.id, day=quota._today(), kind="triage", count=40)); session.commit()
    make_job()
    provider = FakeProvider()
    summary = evaluate_for_user(session, user.id, provider)
    row = next(iter(evals(session, user.id).values()))
    assert (row.disposition, row.reason_code) == ("deferred", "quota_triage")
    assert provider.total_calls == 0 and summary.deferred == 1 and summary.rejected == 0 and summary.conserved
    # next day / more quota: retried, not cached as an answer
    session.query(UsageCounter).delete(); session.commit()
    evaluate_for_user(session, user.id, FakeProvider())
    assert next(iter(evals(session, user.id).values())).disposition == "matched"


def test_deep_match_quota_leaves_jobs_triaged(session, make_user, make_job):
    user = make_user("a@x.com", plan="free")  # 5 deep matches/day
    for _ in range(7):
        make_job()
    provider = FakeProvider()
    summary = evaluate_for_user(session, user.id, provider)
    assert (summary.matched, summary.triaged) == (5, 2) and summary.conserved
    assert provider.calls["analyse_match"] == 5
    assert quota.remaining(session, user.id, "deep_match") == 0


def test_deep_top_n_bounds_stage3(session, make_user, make_job):
    user = make_user("a@x.com")
    for _ in range(4):
        make_job()
    summary = evaluate_for_user(session, user.id, FakeProvider(), deep_top_n=1)
    assert (summary.matched, summary.triaged) == (1, 3)


def test_provider_error_fails_closed_and_refunds(session, make_user, make_job):
    user = make_user("a@x.com")
    make_job()
    summary = evaluate_for_user(session, user.id, FakeProvider(classify=BUDGET_ERROR))
    row = next(iter(evals(session, user.id).values()))
    assert (row.disposition, row.reason_code) == ("deferred", "llm_budget")
    assert summary.rejected == 0 and summary.errored == 0 and summary.conserved
    assert quota.used_today(session, user.id, "triage") == 0  # no verdict, no charge
    evaluate_for_user(session, user.id, FakeProvider(classify=RuntimeError("boom")))
    assert next(iter(evals(session, user.id).values())).disposition == "errored"
    evaluate_for_user(session, user.id, FakeProvider(classify=CircuitOpen("circuit_open")))
    assert next(iter(evals(session, user.id).values())).reason_code == "llm_circuit"


def test_match_stage_failure_keeps_triage_not_rejection(session, make_user, make_job):
    user = make_user("a@x.com")
    make_job()
    summary = evaluate_for_user(session, user.id, FakeProvider(match=BUDGET_ERROR))
    row = next(iter(evals(session, user.id).values()))
    assert row.disposition == "triaged" and row.reason_code == "match_llm_budget" and row.classification
    assert summary.rejected == 0 and summary.conserved
    assert quota.used_today(session, user.id, "deep_match") == 0


def test_one_bad_job_does_not_stop_the_run(session, make_user, make_job):
    user = make_user("a@x.com")
    good, bad = make_job(), make_job()
    bad.normalized = {"nonsense": True}
    session.commit()
    summary = evaluate_for_user(session, user.id, FakeProvider())
    rows = evals(session, user.id)
    assert rows[bad.id].disposition == "errored" and rows[good.id].disposition == "matched" and summary.conserved


def test_max_jobs_limits_work(session, make_user, make_job):
    user = make_user("a@x.com")
    for _ in range(4):
        make_job()
    summary = evaluate_for_user(session, user.id, FakeProvider(), max_jobs=2)
    assert summary.considered == 2 and len(evals(session, user.id)) == 2 and summary.conserved


def test_tenant_isolation(session, make_user, make_job, add_achievement):
    a, b = make_user("a@x.com"), make_user("b@x.com")
    job = make_job(location="Remote - Canada")
    session.add(SearchPrefs(user_id=a.id, data={"countries": ["Canada"]})); session.commit()
    evaluate_for_user(session, a.id, FakeProvider())
    assert evals(session, b.id) == {} and evals(session, a.id)[job.id].disposition == "matched"
    # B (India) evaluates the same shared job independently and is filtered; A's row is unchanged.
    evaluate_for_user(session, b.id, FakeProvider())
    assert evals(session, b.id)[job.id].disposition == "filtered"
    assert evals(session, a.id)[job.id].disposition == "matched"
    assert quota.used_today(session, b.id, "triage") == 0 and quota.used_today(session, a.id, "triage") == 1


def test_deep_match_prompt_uses_users_own_evidence(session, make_user, make_job, add_achievement):
    a, b = make_user("a@x.com"), make_user("b@x.com")
    add_achievement(a.id, title="Alpha RAG platform"); add_achievement(b.id, title="Beta secret project")
    make_job()
    seen = []
    provider = FakeProvider(match=lambda kw: seen.append(kw["messages"][0]["content"]) or MATCH_STRONG)
    evaluate_for_user(session, a.id, provider)
    assert "Alpha RAG platform" in seen[0] and "Beta secret project" not in seen[0]


def test_on_demand_deep_match_is_idempotent(session, make_user, make_job):
    user = make_user("a@x.com")
    job = make_job()
    evaluate_for_user(session, user.id, FakeProvider(), deep_top_n=0)
    assert evals(session, user.id)[job.id].disposition == "triaged"
    provider = FakeProvider()
    row = deep_match_job(session, user.id, job.id, provider)
    assert row.disposition == "matched" and row.match and provider.calls == {"classify_job": 0, "analyse_match": 1}
    again = deep_match_job(session, user.id, job.id, provider)
    assert again.id == row.id and provider.total_calls == 1
    assert quota.used_today(session, user.id, "deep_match") == 1


def test_on_demand_without_prior_triage_and_failures(session, make_user, make_job):
    user = make_user("a@x.com", plan="free")
    job = make_job()
    row = deep_match_job(session, user.id, job.id, FakeProvider())
    assert row.disposition == "matched" and quota.used_today(session, user.id, "triage") == 1
    other = make_job()
    with pytest.raises(BudgetExceeded):
        deep_match_job(session, user.id, other.id, FakeProvider(classify=BUDGET_ERROR))
    assert evals(session, user.id).get(other.id) is None  # nothing stored, nothing rejected
    assert quota.used_today(session, user.id, "triage") == 1  # refunded
    with pytest.raises(LookupError):
        deep_match_job(session, user.id, 9999, FakeProvider())


def test_on_demand_deep_match_quota(session, make_user, make_job):
    user = make_user("a@x.com", plan="free")
    session.add(UsageCounter(user_id=user.id, day=quota._today(), kind="deep_match", count=5)); session.commit()
    job = make_job()
    with pytest.raises(QuotaExceeded):
        deep_match_job(session, user.id, job.id, FakeProvider())
