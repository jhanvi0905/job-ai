"""Gateway behaviour, proven against scripted fakes: zero network, zero cost."""
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests

from jobai.core.ledger.db import Ledger
from jobai.engine.ai.provider import BudgetExceeded, CircuitOpen, LLMError, LLMProvider, SchemaError
from tests.fakes import FakeResponse, FakeSession, ok

CFG = {
    "provider": {"name": "fake", "base_url": "https://fake.invalid/v1", "api_key_env": "AIMLAPI_KEY"},
    "gateway": {"max_attempts": 3, "backoff_base_s": 1.0, "backoff_max_s": 20.0, "circuit_breaker_failures": 2},
    "budget": {"per_run_usd": 1.0, "per_day_usd": 10.0, "max_calls_per_run": 100},
}


def make(script, *, ledger=None, cfg=None, rng=lambda: 0.5, sink=None):
    sleeps: list[float] = []
    session = FakeSession(script)
    run_id = ledger.start_run("test") if ledger is not None else None
    merged = {**CFG, **(cfg or {})}
    provider = LLMProvider(
        ledger, run_id, session=session, sleep=sleeps.append, rng=rng, config=merged, usage_sink=sink
    )
    return provider, session, sleeps, run_id


def chat(provider, **kw):
    args = dict(model="m", messages=[{"role": "user", "content": "hi"}], max_tokens=50, temperature=0,
                workflow="triage", job_id="job-1")
    args.update(kw)
    return provider._chat(**args)


def rows(ledger):
    return ledger.query("SELECT * FROM llm_calls ORDER BY call_id")


# ---------------------------------------------------------------- happy path
def test_success_returns_parsed_json_and_records_everything():
    ledger = Ledger.memory()
    p, session, sleeps, _ = make([ok({"a": 1}, cost=0.0002)], ledger=ledger)
    out = chat(p, prompt_version="classify_v2", context={"jd_chars": 3900})
    assert out == {"a": 1}
    assert session.calls == 1 and sleeps == []
    (r,) = rows(ledger)
    assert (r["outcome"], r["attempt"], r["node"], r["item_id"]) == ("ok", 1, "triage", "job-1")
    assert r["model_requested"] == "m" and r["model_resolved"] == "gpt-4o-mini-2024-07-18"
    assert (r["tokens_in"], r["tokens_out"]) == (120, 30)
    assert r["cost_usd"] == pytest.approx(0.0002)
    assert r["prompt_version"] == "classify_v2" and '"jd_chars": 3900' in r["context_json"]
    assert len(r["input_hash"]) == 16


def test_input_hash_is_stable_and_content_sensitive():
    ledger = Ledger.memory()
    p, *_ = make([ok({}), ok({}), ok({})], ledger=ledger)
    chat(p, messages=[{"role": "user", "content": "same"}])
    chat(p, messages=[{"role": "user", "content": "same"}])
    chat(p, messages=[{"role": "user", "content": "different"}])
    h = [r["input_hash"] for r in rows(ledger)]
    assert h[0] == h[1] != h[2]


# -------------------------------------------------------------------- retries
def test_429_honours_retry_after_and_then_succeeds():
    ledger = Ledger.memory()
    p, session, sleeps, _ = make([FakeResponse(429, headers={"Retry-After": "7"}), ok({"a": 1})], ledger=ledger)
    assert chat(p) == {"a": 1}
    assert sleeps == [7.0] and session.calls == 2
    assert [r["outcome"] for r in rows(ledger)] == ["http_429", "ok"]
    assert [r["attempt"] for r in rows(ledger)] == [1, 2]


def test_retry_after_is_capped_so_a_hostile_server_cannot_stall_us():
    p, _, sleeps, _ = make([FakeResponse(429, headers={"Retry-After": "3600"}), ok({})])
    chat(p)
    assert sleeps == [20.0]


def test_backoff_is_exponential_with_full_jitter():
    p, _, sleeps, _ = make([FakeResponse(503), FakeResponse(503), ok({})], rng=lambda: 0.5)
    chat(p)
    assert sleeps == [0.5, 1.0]  # 0.5 * base*2^0, then 0.5 * base*2^1


def test_jitter_is_bounded_by_the_cap():
    p, _, sleeps, _ = make(
        [FakeResponse(500)] * 2 + [ok({})], rng=lambda: 1.0,
        cfg={"gateway": {**CFG["gateway"], "backoff_max_s": 1.5}},
    )
    chat(p)
    assert sleeps == [1.0, 1.5]


def test_persistent_5xx_gives_up_after_max_attempts_with_one_sleep_fewer():
    ledger = Ledger.memory()
    p, session, sleeps, _ = make([FakeResponse(500, text="boom")] * 3, ledger=ledger)
    with pytest.raises(LLMError) as e:
        chat(p)
    assert e.value.outcome == "http_5xx" and session.calls == 3 and len(sleeps) == 2
    assert [r["outcome"] for r in rows(ledger)] == ["http_5xx"] * 3


def test_client_errors_are_never_retried():
    ledger = Ledger.memory()
    p, session, sleeps, _ = make([FakeResponse(400, text="bad request")], ledger=ledger)
    with pytest.raises(LLMError) as e:
        chat(p)
    assert e.value.outcome == "http_4xx" and session.calls == 1 and sleeps == []


def test_auth_failure_401_is_not_retried():
    p, session, _, _ = make([FakeResponse(401, text="invalid api key")])
    with pytest.raises(LLMError):
        chat(p)
    assert session.calls == 1


@pytest.mark.parametrize("exc,outcome", [
    (requests.Timeout("slow"), "timeout"),
    (requests.ConnectionError("reset"), "connection_error"),
    (requests.exceptions.ConnectTimeout("connect"), "timeout"),
])
def test_transport_errors_are_retried(exc, outcome):
    ledger = Ledger.memory()
    p, session, sleeps, _ = make([exc, ok({"a": 1})], ledger=ledger)
    assert chat(p) == {"a": 1}
    assert [r["outcome"] for r in rows(ledger)] == [outcome, "ok"]


def test_unparseable_content_is_retried_then_fails_as_invalid_json():
    ledger = Ledger.memory()
    p, session, _, _ = make([ok("not json at all")] * 3, ledger=ledger)
    with pytest.raises(LLMError) as e:
        chat(p)
    assert e.value.outcome == "invalid_json" and session.calls == 3


def test_non_object_json_is_invalid_json():
    p, session, _, _ = make([ok("[1,2,3]"), ok({"a": 1})])
    assert chat(p) == {"a": 1}
    assert session.calls == 2


def test_malformed_response_shape_is_invalid_json_not_a_crash():
    p, _, _, _ = make([FakeResponse(200, {"unexpected": True}), ok({"a": 1})])
    assert chat(p) == {"a": 1}


def test_non_json_http_body_is_handled():
    p, _, _, _ = make([FakeResponse(200, json_error=True), ok({"a": 1})])
    assert chat(p) == {"a": 1}


def test_truncated_output_is_not_retried():
    ledger = Ledger.memory()
    p, session, sleeps, _ = make([ok('{"a": 1', finish="length")], ledger=ledger)
    with pytest.raises(LLMError) as e:
        chat(p)
    assert e.value.outcome == "truncated" and session.calls == 1 and sleeps == []


# ------------------------------------------------------------- schema repair
def _needs_field_x(d):
    if "x" not in d:
        raise ValueError("missing required field 'x'")


def test_schema_failure_gets_exactly_one_repair_with_the_error_shown():
    ledger = Ledger.memory()
    p, session, sleeps, _ = make([ok({"y": 1}), ok({"x": 1})], ledger=ledger)
    assert chat(p, validate=_needs_field_x) == {"x": 1}
    assert [r["outcome"] for r in rows(ledger)] == ["schema_invalid", "ok"]
    repair = session.requests[1]["messages"]
    assert repair[-2]["role"] == "assistant" and repair[-1]["role"] == "user"
    assert "missing required field 'x'" in repair[-1]["content"]
    assert sleeps == []  # a repair is not a transient failure: no backoff


def test_second_schema_failure_raises_and_never_repairs_twice():
    p, session, _, _ = make([ok({"y": 1}), ok({"z": 1}), ok({"x": 1})])
    with pytest.raises(SchemaError):
        chat(p, validate=_needs_field_x)
    assert session.calls == 2


def test_repair_attempt_still_bills_and_is_visible():
    ledger = Ledger.memory()
    p, *_ = make([ok({"y": 1}, cost=0.001), ok({"x": 1}, cost=0.001)], ledger=ledger)
    chat(p, validate=_needs_field_x)
    assert ledger.spent_in_run(rows(ledger)[0]["run_id"]) == pytest.approx(0.002)


# ------------------------------------------------------------------- budgets
def _preload(ledger, run_id, cost, n=1, outcome="ok"):
    for _ in range(n):
        ledger.record_call(run_id=run_id, node="triage", attempt=1, model_requested="m", outcome=outcome, cost_usd=cost)


def test_per_run_budget_blocks_before_any_http_call():
    ledger = Ledger.memory()
    p, session, _, run_id = make([ok({})], ledger=ledger, cfg={"budget": {**CFG["budget"], "per_run_usd": 0.01}})
    _preload(ledger, run_id, 0.01)
    with pytest.raises(BudgetExceeded):
        chat(p)
    assert session.calls == 0
    assert rows(ledger)[-1]["outcome"] == "budget_exceeded" and "per_run" in rows(ledger)[-1]["detail"]


def test_per_day_budget_counts_spend_from_earlier_runs_today():
    ledger = Ledger.memory()
    earlier = ledger.start_run("earlier")
    _preload(ledger, earlier, 0.30)
    p, session, _, _ = make([ok({})], ledger=ledger, cfg={"budget": {**CFG["budget"], "per_day_usd": 0.30}})
    with pytest.raises(BudgetExceeded):
        chat(p)
    assert session.calls == 0 and "per_day" in rows(ledger)[-1]["detail"]


def test_call_count_backstop_for_providers_that_report_no_cost():
    ledger = Ledger.memory()
    p, session, _, run_id = make([ok({})], ledger=ledger, cfg={"budget": {**CFG["budget"], "max_calls_per_run": 3}})
    _preload(ledger, run_id, 0.0, n=3)
    with pytest.raises(BudgetExceeded):
        chat(p)
    assert session.calls == 0 and "max_calls" in rows(ledger)[-1]["detail"]


def test_budget_is_enforced_mid_run_not_just_at_the_start():
    ledger = Ledger.memory()
    p, session, _, _ = make(
        [ok({}, cost=0.0002)] * 5, ledger=ledger, cfg={"budget": {**CFG["budget"], "per_run_usd": 0.0003}}
    )
    chat(p)
    chat(p)  # cumulative 0.0004 >= 0.0003
    with pytest.raises(BudgetExceeded):
        chat(p)
    assert session.calls == 2


def test_blocked_calls_are_not_counted_toward_the_call_backstop():
    ledger = Ledger.memory()
    p, _, _, run_id = make([ok({})], ledger=ledger, cfg={"budget": {**CFG["budget"], "per_run_usd": 0.0}})
    with pytest.raises(BudgetExceeded):
        chat(p)
    assert ledger.calls_in_run(run_id) == 0


def test_no_ledger_means_no_budget_enforcement_but_retries_still_work():
    p, session, sleeps, _ = make([FakeResponse(500), ok({"a": 1})])
    assert chat(p) == {"a": 1}
    assert session.calls == 2


# ----------------------------------------------------------- circuit breaker
def test_circuit_opens_after_consecutive_failed_calls_and_stops_all_http():
    ledger = Ledger.memory()
    p, session, _, _ = make([FakeResponse(400), FakeResponse(400), ok({})], ledger=ledger)
    for _ in range(2):  # breaker threshold is 2
        with pytest.raises(LLMError):
            chat(p)
    with pytest.raises(CircuitOpen):
        chat(p)
    assert session.calls == 2
    assert rows(ledger)[-1]["outcome"] == "circuit_open"


def test_a_success_resets_the_breaker():
    p, session, _, _ = make([FakeResponse(400), ok({}), FakeResponse(400), ok({})])
    with pytest.raises(LLMError):
        chat(p)
    chat(p)
    with pytest.raises(LLMError):
        chat(p)
    chat(p)  # would raise CircuitOpen if the counter had not reset
    assert session.calls == 4


# ------------------------------------------------------------ cost handling
def test_cost_is_estimated_from_pricing_config_when_provider_reports_none():
    ledger = Ledger.memory()
    body = ok({"a": 1}, prompt_tokens=1000, completion_tokens=500)
    del body._body["meta"]
    cfg = {"pricing": {"m": {"in_per_mtok": 1.0, "out_per_mtok": 2.0}}}
    p, *_ = make([body], ledger=ledger, cfg=cfg)
    chat(p)
    assert rows(ledger)[0]["cost_usd"] == pytest.approx(0.002)


def test_unknown_cost_is_recorded_as_zero_not_invented():
    ledger = Ledger.memory()
    body = ok({"a": 1})
    del body._body["meta"]
    p, *_ = make([body], ledger=ledger)
    chat(p)
    assert rows(ledger)[0]["cost_usd"] == 0.0


def test_usage_sink_sees_every_attempt_including_failures():
    seen = []
    p, *_ = make([FakeResponse(500), ok({"a": 1})], sink=seen.append)
    chat(p)
    assert [(s.success, s.error) for s in seen] == [(False, "http_5xx"), (True, None)]


# --------------------------------------------------------------- concurrency
def test_thread_pool_use_records_every_call_without_loss():
    ledger = Ledger.memory()
    p, session, _, run_id = make([ok({"a": 1}, cost=0.0001)] * 60, ledger=ledger)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda i: chat(p, job_id=f"job-{i}"), range(60)))
    assert all(r == {"a": 1} for r in results)
    assert ledger.calls_in_run(run_id) == 60
    assert ledger.spent_in_run(run_id) == pytest.approx(0.006)
