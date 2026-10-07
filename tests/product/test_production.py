"""Production hardening: task queue + worker, rate limits, request ids, security
headers, body cap, docs lockdown, health/readiness, Sentry scrubbing, JSON logs,
pricing coverage and the migration chain."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from jobai.core.config import load_models
from jobai.engine.ai.provider import LLMError
from jobai.product import observability
from jobai.product.api.app import create_app
from jobai.product.db.models import RateLimitCounter, Task, User, WorkerHeartbeat
from jobai.product.db.session import make_session_factory
from jobai.product.services import ratelimit
from jobai.product.services import tasks as tasks_svc
from jobai.product.services.resume import LocalStorage
from jobai.product.worker import Worker, execute, run_until_idle, schedule
from tests.product.api_helpers import *  # noqa: F401,F403
from tests.product.api_helpers import PARSED, FakeLLM, drain, local_verifier, signup, upload

ROOT = Path(__file__).resolve().parents[2]


def _user(session_factory, email="u@example.com", plan="free", **kw) -> int:
    with session_factory() as s:
        u = User(email=email, plan=plan, **kw)
        s.add(u)
        s.commit()
        return u.id


# ------------------------------------------------------------------ task queue
def test_enqueue_dedupes_active_feed_refresh_per_user(session_factory):
    uid, other = _user(session_factory), _user(session_factory, "o@example.com")
    with session_factory() as s:
        t1, c1 = tasks_svc.enqueue(s, "feed_refresh", user_id=uid)
        t2, c2 = tasks_svc.enqueue(s, "feed_refresh", user_id=uid)
        t3, c3 = tasks_svc.enqueue(s, "feed_refresh", user_id=other)
        p1, _ = tasks_svc.enqueue(s, "resume_parse", user_id=uid, payload={"resume_id": 1})
        p2, _ = tasks_svc.enqueue(s, "resume_parse", user_id=uid, payload={"resume_id": 1})
        s.commit()
        assert (c1, c2, c3) == (True, False, True) and t1.id == t2.id != t3.id
        assert p1.id != p2.id  # parses are not deduplicated
        tasks_svc.complete(s, t1.id, {"ok": 1})
        t4, c4 = tasks_svc.enqueue(s, "feed_refresh", user_id=uid)
        assert c4 and t4.id != t1.id  # a finished task frees the key


def test_claim_fail_backoff_then_terminal(session_factory):
    uid = _user(session_factory)
    with session_factory() as s:
        task, _ = tasks_svc.enqueue(s, "feed_refresh", user_id=uid)
        s.commit()
        tid = task.id
    with session_factory() as s:
        claimed = tasks_svc.claim(s, "w1")
        assert claimed.id == tid and claimed.status == "running" and claimed.attempts == 1
        assert tasks_svc.claim(s, "w2") is None  # nothing else due
        assert tasks_svc.fail(s, tid, "llm_error: timeout") == "queued"
        row = s.get(Task, tid)
        assert row.dedupe_key is not None and tasks_svc._aware(row.run_after) > datetime.now(UTC)
        assert tasks_svc.claim(s, "w1") is None  # backoff: not due yet
        future = datetime.now(UTC) + timedelta(hours=2)
        for attempt in (2, 3):
            assert tasks_svc.claim(s, "w1", now=future).attempts == attempt
            status = tasks_svc.fail(s, tid, "llm_error: timeout")
        assert status == "failed"
        row = s.get(Task, tid)
        s.refresh(row)
        assert row.finished_at is not None and row.dedupe_key is None


def test_non_retryable_failure_is_terminal_immediately(session_factory):
    uid = _user(session_factory)
    with session_factory() as s:
        task, _ = tasks_svc.enqueue(s, "resume_parse", user_id=uid, payload={"resume_id": 999})
        s.commit()
    run_until_idle(session_factory, lambda u, r: FakeLLM({}))
    with session_factory() as s:
        row = s.get(Task, task.id)
        assert row.status == "failed" and row.error == "resume_not_found" and row.attempts == 1


def test_reaper_requeues_stale_running_tasks(session_factory):
    uid = _user(session_factory)
    with session_factory() as s:
        task, _ = tasks_svc.enqueue(s, "feed_refresh", user_id=uid)
        s.commit()
        tasks_svc.claim(s, "dead-worker")
        assert tasks_svc.reap_stale(s) == 0  # fresh lock: leave it alone
        assert tasks_svc.reap_stale(s, now=datetime.now(UTC) + timedelta(hours=1)) == 1
        row = s.get(Task, task.id)
        s.refresh(row)
        assert row.status == "queued" and row.locked_at is None and "lock expired" in row.error


def test_release_returns_task_without_counting_attempt(session_factory):
    uid = _user(session_factory)
    with session_factory() as s:
        task, _ = tasks_svc.enqueue(s, "feed_refresh", user_id=uid)
        s.commit()
        tasks_svc.claim(s, "w")
        tasks_svc.release(s, task.id)
        row = s.get(Task, task.id)
        s.refresh(row)
        assert row.status == "queued" and row.attempts == 0


def test_llm_outage_is_retried_then_succeeds(client, app):
    h = signup(client)
    flaky = FakeLLM({"parse_resume": PARSED})
    calls = {"n": 0}
    real = flaky._chat

    def chat(**kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise LLMError("timeout", "upstream")
        return real(**kw)
    flaky._chat = chat
    app.state.provider_factory = lambda uid, rid: flaky
    r = upload(client, h)
    task = client.get(f"/tasks/{r.json()['task_id']}", headers=h).json()
    assert task["status"] == "queued" and task["error"] is None  # retry pending, error not exposed yet
    with app.state.session_factory() as s:  # make the retry due now
        row = s.get(Task, uuid.UUID(task["id"]))
        row.run_after = datetime.now(UTC) - timedelta(seconds=1)
        s.commit()
    drain(client)
    task = client.get(f"/tasks/{task['id']}", headers=h).json()
    assert task["status"] == "succeeded" and task["result"] == {"achievements": 2}


def test_get_task_is_owner_only(client):
    alice, bob = signup(client, "alice@example.com"), signup(client, "bob@example.com")
    tid = client.post("/feed/refresh", headers=alice).json()["task_id"]
    assert client.get(f"/tasks/{tid}", headers=alice).status_code == 200
    assert client.get(f"/tasks/{tid}", headers=bob).status_code == 404
    assert client.get("/tasks/not-a-uuid", headers=alice).status_code == 404
    assert client.get(f"/tasks/{uuid.uuid4()}", headers=alice).status_code == 404
    assert client.get(f"/tasks/{tid}").status_code == 401


def test_feed_refresh_contract(client):
    h = signup(client)
    r = client.post("/feed/refresh", headers=h)
    assert r.status_code == 202 and set(r.json()) == {"task_id", "status"} and r.json()["status"] == "queued"
    body = client.get(f"/tasks/{r.json()['task_id']}", headers=h).json()
    assert set(body) == {"id", "kind", "status", "result", "error", "created_at", "finished_at"}
    assert body["kind"] == "feed_refresh" and body["result"] is None


def test_resume_upload_contract_and_parse_quota_precheck(client):
    h = signup(client)  # free plan: 2 parses/day
    r = upload(client, h, run_tasks=False)
    assert r.status_code == 201 and set(r.json()) == {"resume", "task_id"} and r.json()["resume"]["chars"] > 0
    assert client.get("/achievements", headers=h).json() == []  # not parsed until the worker runs
    assert upload(client, h, b"second resume, long enough to be parsed fine", run_tasks=False).status_code == 201
    # Two parses already queued: the third is refused up front, nothing stored.
    third = upload(client, h, b"third resume, long enough to be parsed fine", run_tasks=False)
    assert third.status_code == 429 and third.json()["error"]["code"] == "quota_exceeded"
    assert drain(client) == 2
    assert len(client.get("/achievements", headers=h).json()) == 2


def test_erasure_removes_tasks(client, session_factory):
    h = signup(client)
    client.post("/feed/refresh", headers=h)
    assert client.delete("/me", headers=h).status_code == 204
    with session_factory() as s:
        assert s.query(Task).count() == 0


# ------------------------------------------------------------------- scheduler
def test_scheduler_ingest_interval_and_daily_refresh_for_active_users(session_factory):
    now = datetime.now(UTC)
    active = _user(session_factory, "active@example.com", last_seen_at=now - timedelta(days=2))
    _user(session_factory, "stale@example.com", last_seen_at=now - timedelta(days=30))
    _user(session_factory, "never@example.com")
    out = schedule(session_factory, now=now, ingest_interval=timedelta(minutes=360))
    assert out == {"catalog_ingest": 1, "feed_refresh": 1}
    with session_factory() as s:
        assert s.query(Task).filter_by(kind="feed_refresh").one().user_id == active
    # Same tick again: everything already scheduled.
    assert schedule(session_factory, now=now, ingest_interval=timedelta(minutes=360)) == {"catalog_ingest": 0, "feed_refresh": 0}
    # Next day: ingest is due again (once finished); the refresh is due again too.
    with session_factory() as s:
        for t in s.query(Task).all():
            tasks_svc.complete(s, t.id, {})
    later = now + timedelta(hours=25)
    assert schedule(session_factory, now=later, ingest_interval=timedelta(minutes=360)) == {"catalog_ingest": 1, "feed_refresh": 1}


def test_scheduler_respects_exhausted_triage_quota(session_factory):
    from jobai.product.services import quota
    uid = _user(session_factory, last_seen_at=datetime.now(UTC))
    with session_factory() as s:
        quota.consume(s, uid, "triage", quota.PLAN_LIMITS["free"]["triage"])
        s.commit()
    assert schedule(session_factory)["feed_refresh"] == 0


def test_last_seen_is_recorded_on_authenticated_requests(client, session_factory):
    signup(client)
    with session_factory() as s:
        assert s.query(User).one().last_seen_at is not None


def test_worker_loop_runs_tasks_heartbeats_and_stops(session_factory):
    uid = _user(session_factory)
    with session_factory() as s:
        tasks_svc.enqueue(s, "resume_parse", user_id=uid, payload={"resume_id": 1})
        s.commit()
    w = Worker(session_factory, provider_factory=lambda u, r: FakeLLM({}), poll_interval_s=0.01, schedule_enabled=False)
    original = w.housekeeping
    ticks = {"n": 0}

    def housekeeping():
        original()
        ticks["n"] += 1
        if ticks["n"] >= 3:
            w.stop.set()
    w.housekeeping = housekeeping
    w.run_forever()
    with session_factory() as s:
        assert s.query(Task).one().status == "failed"  # resume 1 does not exist -> non-retryable
        assert s.get(WorkerHeartbeat, w.worker_id) is not None


def test_execute_never_raises(session_factory):
    uid = _user(session_factory)
    with session_factory() as s:
        task, _ = tasks_svc.enqueue(s, "feed_refresh", user_id=uid)
        s.commit()
        claimed = tasks_svc.claim(s, "w")

    def boom(u, r):
        raise RuntimeError("secret resume text must not leak")
    assert execute(session_factory, claimed, boom) == "queued"
    with session_factory() as s:
        assert s.get(Task, task.id).error == "internal_error"


# ----------------------------------------------------------------- rate limits
@pytest.fixture
def limited(app):
    app.state.rate_limits_enabled = True
    return app


def test_waitlist_limited_per_ip(limited, client):
    for i in range(5):
        assert client.post("/waitlist", json={"email": f"w{i}@example.com"}, headers={"Fly-Client-IP": "1.2.3.4"}).status_code == 204
    r = client.post("/waitlist", json={"email": "w9@example.com"}, headers={"Fly-Client-IP": "1.2.3.4"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    assert 0 < int(r.headers["Retry-After"]) <= 3600
    assert client.post("/waitlist", json={"email": "x@example.com"}, headers={"Fly-Client-IP": "5.6.7.8"}).status_code == 204


def test_feed_refresh_limited_per_user(limited, client, session_factory):
    h = signup(client)
    for _ in range(6):
        assert client.post("/feed/refresh", headers=h).status_code == 202
    assert client.post("/feed/refresh", headers=h).status_code == 429
    other = signup(client, "b@example.com")
    assert client.post("/feed/refresh", headers=other).status_code == 202


def test_authenticated_write_limit(limited, client, monkeypatch):
    monkeypatch.setitem(ratelimit.RULES, "write", ratelimit.Rule(3, 60))
    h = signup(client)
    for _ in range(3):
        assert client.put("/prefs", headers=h, json={}).status_code == 200
    assert client.put("/prefs", headers=h, json={}).status_code == 429
    assert client.get("/prefs", headers=h).status_code == 200  # reads are not write-limited


def test_rate_limit_window_counts(session_factory):
    rule = ratelimit.Rule(2, 60)
    t0 = datetime(2026, 1, 1, 12, 0, 10, tzinfo=UTC)
    assert ratelimit.hit(session_factory, "k", rule, t0) == (1, 50)
    assert ratelimit.hit(session_factory, "k", rule, t0 + timedelta(seconds=5))[0] == 2
    assert ratelimit.hit(session_factory, "k", rule, t0 + timedelta(seconds=60))[0] == 1  # next window
    with session_factory() as s:
        assert s.query(RateLimitCounter).count() == 2


# ----------------------------------------------------- headers, ids, body, docs
def test_request_id_and_security_headers(client):
    r = client.get("/health")
    assert len(r.headers["x-request-id"]) == 32
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert "strict-transport-security" not in r.headers  # dev
    assert client.get("/health", headers={"X-Request-ID": "abc-123"}).headers["x-request-id"] == "abc-123"
    assert client.get("/health", headers={"X-Request-ID": "bad id\n"}).headers["x-request-id"] != "bad id\n"


def test_body_size_limit(client):
    h = signup(client)
    r = client.post("/resume", headers=h, files={"file": ("a.txt", b"x" * (3 * 1024 * 1024 + 10), "text/plain")})
    assert r.status_code == 413 and r.json()["error"]["code"] == "too_large"


def test_prod_hardening(monkeypatch, session_factory, tmp_path):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        create_app(session_factory, storage=LocalStorage(tmp_path), token_verifier=local_verifier())
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    c = TestClient(create_app(session_factory, storage=LocalStorage(tmp_path), token_verifier=local_verifier()))
    assert c.get("/docs").status_code == 404 and c.get("/openapi.json").status_code == 404
    r = c.get("/health")
    assert r.headers["strict-transport-security"].startswith("max-age=")
    pre = c.options("/me", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in pre.headers
    ok = c.options("/me", headers={"Origin": "https://app.example.com", "Access-Control-Request-Method": "GET",
                                   "Access-Control-Request-Headers": "authorization"})
    assert ok.headers["access-control-allow-origin"] == "https://app.example.com"


def test_unhandled_error_is_json_with_request_id(app):
    @app.get("/__boom")
    def boom():
        raise RuntimeError("kaboom")
    r = TestClient(app, raise_server_exceptions=False).get("/__boom", headers={"X-Request-ID": "rid-1"})
    assert r.status_code == 500 and r.json()["error"] == {"code": "internal_error", "message": "internal error", "request_id": "rid-1"}


# --------------------------------------------------------------- health/ready
def test_ready_reports_unmigrated_db_as_not_ready(client):
    assert client.get("/health").json() == {"status": "ok"}
    r = client.get("/ready")
    assert r.status_code == 503 and r.json()["checks"]["database"] == "ok" and r.json()["checks"]["migrations"] != "ok"


def _migrate(url: str) -> None:
    from alembic import command
    from alembic.config import Config
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    command.check(cfg)  # models and migrations agree (raises on drift)


def test_migrations_reach_head_match_models_and_ready_is_200(tmp_path):
    url = f"sqlite:///{tmp_path / 'mig.db'}"
    _migrate(url)
    sf = make_session_factory(create_engine(url))
    app = create_app(sf, storage=LocalStorage(tmp_path), token_verifier=local_verifier())
    with sf() as s:
        s.add(WorkerHeartbeat(worker_id="w", last_seen_at=datetime.now(UTC)))
        s.commit()
    body = TestClient(app).get("/ready").json()
    assert body["status"] == "ready" and body["checks"]["migrations"] == "ok" and body["checks"]["worker_last_seen_s"] <= 5


# --------------------------------------------------------------- observability
def test_sentry_scrubber_removes_secrets_and_content():
    event = {
        "request": {"headers": {"Authorization": "Bearer abc.def.ghi", "User-Agent": "x"}, "data": {"text": "resume"},
                    "cookies": {"sb": "1"}, "query_string": "token=1"},
        "extra": {"description": "Senior ML Engineer JD...", "job_id": 7, "nested": {"resume_text": "me"}},
        "exception": {"values": [{"value": "failed with Bearer eyJhbGciOiJFUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.sig_sig_sig",
                                  "stacktrace": {"frames": [{"vars": {"text": "resume"}}]}}]},
        "breadcrumbs": {"values": [{"message": "auth Bearer tok123", "data": {"prompt": "secret"}}]},
    }
    out = observability.scrub_event(event)
    assert out["request"]["headers"]["Authorization"] == "[Filtered]" and out["request"]["headers"]["User-Agent"] == "x"
    assert "data" not in out["request"] and "cookies" not in out["request"] and "query_string" not in out["request"]
    assert out["extra"]["description"] == "[Filtered]" and out["extra"]["job_id"] == 7
    assert out["extra"]["nested"]["resume_text"] == "[Filtered]"
    assert "eyJ" not in out["exception"]["values"][0]["value"]
    assert "vars" not in out["exception"]["values"][0]["stacktrace"]["frames"][0]
    assert "tok123" not in out["breadcrumbs"]["values"][0]["message"]
    assert out["breadcrumbs"]["values"][0]["data"]["prompt"] == "[Filtered]"


def test_init_sentry_is_noop_without_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert observability.init_sentry("api") is False


def test_json_log_lines_carry_request_and_user_ids(client, capsys):
    h = signup(client)
    observability.configure_logging("api")  # rebind the handler to pytest's captured stdout
    capsys.readouterr()
    client.get("/me", headers={**h, "X-Request-ID": "req-42"})
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    access = [line for line in lines if line.get("logger") == "product.access" and line.get("request_id") == "req-42"]
    assert access and access[0]["user_id"] is not None and access[0]["path"] == "/me" and access[0]["status"] == 200
    assert all("Bearer" not in json.dumps(line) or "[Filtered]" in json.dumps(line) for line in lines)


def test_json_formatter_redacts_tokens_and_sensitive_extras():
    rec = logging.makeLogRecord({"msg": "got Bearer abc.def", "levelno": 20, "levelname": "INFO", "name": "x"})
    rec.description = "full JD text"
    rec.job_id = 3
    out = json.loads(observability.JsonFormatter("api").format(rec))
    assert "abc.def" not in out["msg"] and out["description"] == "[Filtered]" and out["job_id"] == 3


# --------------------------------------------------------------------- pricing
def test_every_routed_model_has_a_price():
    cfg = load_models()
    missing = {r["model"] for r in cfg["routing"].values() if r.get("model")} - set(cfg.get("pricing", {}))
    assert not missing, f"add {sorted(missing)} to config/models.yaml pricing (else the $ guard books $0)"
    for price in cfg["pricing"].values():
        assert price["in_per_mtok"] > 0 and price["out_per_mtok"] > 0


def test_unpriced_model_warns_once(caplog):
    from jobai.engine.ai import provider as provider_mod
    p = provider_mod.LLMProvider(config={"provider": {"name": "x", "base_url": "http://x", "api_key_env": "NOPE"}})
    provider_mod._UNPRICED_WARNED.discard("mystery-model")
    with caplog.at_level(logging.WARNING, logger="jobai.engine.ai.provider"):
        assert p._cost({}, "mystery-model", 10, 10) == 0.0
        p._cost({}, "mystery-model", 10, 10)
    assert sum("mystery-model" in r.getMessage() for r in caplog.records) == 1

