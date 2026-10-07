import pytest
from sqlalchemy import select

from jobai.engine.ai.provider import BudgetExceeded
from jobai.product.db.models import LLMCall
from jobai.product.services.llm import make_user_provider
from tests.fakes import FakeSession, ok


def chat(provider, job_id="j1"):
    return provider._chat(model="m", messages=[{"role": "user", "content": "hi"}], max_tokens=10, temperature=0,
                          workflow="classify_job", job_id=job_id)


def test_calls_are_recorded_against_the_user(factory, session, make_user):
    user = make_user("a@x.com")
    http = FakeSession([ok({"a": 1}, cost=0.002)])
    assert chat(make_user_provider(factory, user.id, "run1", http_session=http)) == {"a": 1}
    row = session.scalar(select(LLMCall))
    assert (row.user_id, row.run_id, row.node, row.outcome, row.cost_usd) == (user.id, "run1", "classify_job", "ok", 0.002)


def test_daily_guard_is_per_user_and_makes_no_http_call(factory, session, make_user):
    a, b = make_user("a@x.com"), make_user("b@x.com")
    session.add(LLMCall(user_id=a.id, run_id="old", node="classify_job", model="m", cost_usd=5.0, outcome="ok"))
    session.commit()
    blocked_http = FakeSession([])
    with pytest.raises(BudgetExceeded):
        chat(make_user_provider(factory, a.id, "r", http_session=blocked_http))
    assert blocked_http.calls == 0
    # the block itself is recorded (and costs nothing)
    assert session.scalar(select(LLMCall).where(LLMCall.user_id == a.id, LLMCall.outcome == "budget_exceeded"))
    # user B's spend is untouched by A's
    assert chat(make_user_provider(factory, b.id, "r2", http_session=FakeSession([ok({"ok": True})]))) == {"ok": True}


def test_missing_run_id_still_gets_budget_guard(factory, make_user):
    user = make_user("a@x.com")
    provider = make_user_provider(factory, user.id)
    assert provider.run_id  # a run id is always set, so the gateway can never skip its guards
