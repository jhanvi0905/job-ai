"""Auth flows + tenant isolation on every owned resource."""
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from jobai.product.db.models import Application, User
from jobai.product.services import auth as auth_svc
from tests.product.api_helpers import *  # noqa: F401,F403  (fixtures)
from tests.product.api_helpers import bearer, local_verifier, mint_token, signup, upload


def test_first_request_provisions_me(client):
    h = signup(client)
    me = client.get("/me", headers=h).json()
    assert set(me) == {"id", "email", "plan", "created_at"}
    assert me["email"] == "a@example.com" and me["plan"] == "free"
    assert client.get("/me", headers=bearer(mint_token("a@example.com"))).json()["id"] == me["id"]  # same identity


def test_signup_and_login_routes_are_gone(client):
    assert client.post("/auth/signup", json={"email": "a@example.com", "password": "password123"}).status_code in (404, 405)
    assert client.post("/auth/login", json={"email": "a@example.com", "password": "password123"}).status_code in (404, 405)


def test_bad_tokens_rejected(client):
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    other_key = ec.generate_private_key(ec.SECP256R1())
    assert client.get("/me", headers=bearer(mint_token(key=other_key))).status_code == 401
    r = client.get("/me")
    assert r.json()["error"]["code"] == "unauthorized" and r.headers["www-authenticate"] == "Bearer"


def test_auth_required_outside_dev(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    with pytest.raises(RuntimeError):
        auth_svc.check_auth_config(None)
    auth_svc.check_auth_config(local_verifier())
    monkeypatch.setenv("APP_ENV", "dev")
    auth_svc.check_auth_config(None)  # dev: warns, every authed route 401s


def test_waitlist_public_and_idempotent(client):
    for _ in range(2):
        assert client.post("/waitlist", json={"email": "w@example.com", "source": "lp"}).status_code == 204


def test_tenant_isolation(client, session_factory, job, llm):
    alice, bob = signup(client, "alice@example.com"), signup(client, "bob@example.com")
    up = upload(client, alice)
    assert up.status_code == 201
    ach_id = client.get("/achievements", headers=alice).json()[0]["id"]
    # Bob sees none of Alice's data and cannot touch it.
    assert client.get("/achievements", headers=bob).json() == []
    assert client.get("/resume", headers=bob).json() is None
    assert client.patch(f"/achievements/{ach_id}", headers=bob, json={"title": "x"}).status_code == 404
    assert client.delete(f"/achievements/{ach_id}", headers=bob).status_code == 404
    assert len(client.get("/achievements", headers=alice).json()) == 2

    # Tailor runs
    run = client.post(f"/jobs/{job}/tailor", headers=alice)
    assert run.status_code == 200, run.text
    rid = run.json()["run_id"]
    for call in (lambda: client.post(f"/tailor/{rid}/accept", headers=bob, json={"indices": [0]}),
                 lambda: client.get(f"/tailor/{rid}/download", headers=bob)):
        assert call().status_code == 404
    assert client.post(f"/jobs/{job}/tailor", headers=bob).status_code == 400  # bob has no resume

    # Applications and feed
    assert client.put(f"/applications/{job}", headers=alice, json={"status": "applied"}).status_code == 200
    assert client.get("/applications", headers=bob).json() == []
    assert len(client.get("/applications", headers=alice).json()) == 1
    assert client.get("/feed", headers=bob).json() == {"items": [], "total": 0}


def test_feed_returns_only_own_evaluations(client, session_factory, job):
    from jobai.product.db.models import UserJobEvaluation
    alice, bob = signup(client, "alice@example.com"), signup(client, "bob@example.com")
    with session_factory() as s:
        uid = s.query(User).filter_by(email="alice@example.com").one().id
        s.add(UserJobEvaluation(user_id=uid, job_id=job, disposition="matched", fit="strong", fit_rank=3, jd_hash="h",
                                rules_sig="r", match={"reason": "great", "gaps": ["go"]}))
        s.commit()
    item = client.get("/feed", headers=alice).json()["items"][0]
    assert item["why_fits"] == "great" and item["gaps"] == ["go"] and item["fit"] == "strong"
    assert client.get("/feed?min_fit=strong", headers=alice).json()["total"] == 1
    assert client.get("/feed", headers=bob).json()["total"] == 0
    assert client.get(f"/jobs/{job}", headers=bob).json()["evaluation"] is None
    assert client.get(f"/jobs/{job}", headers=alice).json()["evaluation"]["gaps"] == ["go"]


def test_erasure_deletes_everything(client, session_factory, job, tmp_path):
    h = signup(client)
    upload(client, h)
    client.put(f"/applications/{job}", headers=h, json={"status": "saved"})
    assert (tmp_path / "uploads").exists() and any((tmp_path / "uploads").rglob("*.txt"))
    assert client.delete("/me", headers=h).status_code == 204
    assert client.get("/me", headers=h).status_code == 401
    with session_factory() as s:
        assert s.query(User).count() == 0 and s.query(Application).count() == 0
    assert not any((tmp_path / "uploads").rglob("*.txt"))
