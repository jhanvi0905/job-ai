"""Supabase integration, fully offline: token verification (JWKS / legacy HS256),
just-in-time provisioning, account erasure through the Auth Admin API, Storage
over a mocked transport, pooler-safe engines and the RLS coverage tripwire."""
from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from jobai.product.api.app import create_app
from jobai.product.db.models import Base, ErasedAccount, ResumeVersion, User
from jobai.product.db.session import make_engine
from jobai.product.services import auth as auth_svc
from jobai.product.services.resume import LocalStorage, StorageError, SupabaseStorage
from tests.product.api_helpers import *  # noqa: F401,F403  (fixtures)
from tests.product.api_helpers import (
    TEST_ISSUER,
    TEST_KID,
    TEST_PUBLIC_KEY,
    TEST_SUPABASE_URL,
    auth_id_for,
    bearer,
    local_verifier,
    mint_token,
    signup,
    upload,
)

ROOT = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------ verification
def test_verifier_checks_audience_issuer_expiry_and_algorithm():
    verify = local_verifier()
    assert verify(mint_token())["email"] == "a@example.com"
    for bad in (mint_token(aud="anon"), mint_token(iss="https://evil.supabase.co/auth/v1"), mint_token(ttl=-120),
                jwt.encode({"sub": str(uuid.uuid4()), "aud": "authenticated", "iss": TEST_ISSUER, "exp": 9999999999},
                           None, algorithm="none")):
        with pytest.raises(auth_svc.AuthError):
            verify(bad)


def test_rs256_key_from_jwks_is_accepted_and_unknown_kid_rejected():
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(rsa_key.public_key()))
    ec_jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(TEST_PUBLIC_KEY))
    verify = auth_svc.SupabaseVerifier(TEST_SUPABASE_URL)
    assert verify.jwks_url == f"{TEST_SUPABASE_URL}/auth/v1/.well-known/jwks.json"
    verify._jwks = jwt.PyJWKClient(verify.jwks_url, cache_keys=True)
    verify._jwks.fetch_data = lambda: {"keys": [{**jwk, "kid": "rsa-1", "alg": "RS256", "use": "sig"},
                                                {**ec_jwk, "kid": TEST_KID, "alg": "ES256", "use": "sig"}]}
    assert verify(mint_token(key=rsa_key, alg="RS256", kid="rsa-1"))["aud"] == "authenticated"
    assert verify(mint_token())["email"] == "a@example.com"  # the EC key, selected by kid
    with pytest.raises(auth_svc.AuthError):
        verify(mint_token(key=rsa_key, alg="RS256", kid="unknown"))


def test_legacy_hs256_needs_the_project_secret():
    secret = "legacy-project-jwt-secret-0123456789abcdef"
    tok = mint_token(key=secret, alg="HS256")
    with pytest.raises(auth_svc.AuthError):
        local_verifier()(tok)
    assert local_verifier(jwt_secret=secret)(tok)["sub"] == str(auth_id_for("a@example.com"))
    with pytest.raises(auth_svc.AuthError):
        local_verifier(jwt_secret="a-different-secret-0123456789abcdef")(tok)


def test_verifier_from_env(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    assert auth_svc.verifier_from_env() is None
    monkeypatch.setenv("SUPABASE_URL", "https://abc.supabase.co/")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "s")
    v = auth_svc.verifier_from_env()
    assert v.issuer == "https://abc.supabase.co/auth/v1" and v.jwt_secret == "s"


def test_wrong_audience_and_expired_tokens_are_401(client):
    for tok in (mint_token(aud="anon"), mint_token(ttl=-120), mint_token(is_anonymous=True), mint_token(sub="not-a-uuid")):
        r = client.get("/me", headers=bearer(tok))
        assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


def test_no_verifier_configured_means_401(session_factory, tmp_path):
    c = TestClient(create_app(session_factory, storage=LocalStorage(tmp_path)))
    assert c.get("/me", headers=bearer(mint_token())).status_code == 401


# ------------------------------------------------------------ provisioning
def test_user_provisioned_exactly_once(client, session_factory):
    for _ in range(3):
        assert client.get("/me", headers=bearer(mint_token("New@Example.com"))).status_code == 200
    with session_factory() as s:
        users = s.query(User).all()
        assert len(users) == 1
        assert users[0].email == "new@example.com" and users[0].auth_id == auth_id_for("New@Example.com")
        assert users[0].plan == "free" and users[0].password_hash is None


def test_legacy_row_with_same_email_is_linked_not_duplicated(client, session_factory):
    with session_factory() as s:
        s.add(User(email="old@example.com", password_hash="scrypt$legacy", plan="pro"))
        s.commit()
    me = client.get("/me", headers=bearer(mint_token("old@example.com"))).json()
    assert me["plan"] == "pro"
    with session_factory() as s:
        assert s.query(User).count() == 1 and s.query(User).one().auth_id == auth_id_for("old@example.com")


def test_email_owned_by_another_identity_is_409(client):
    signup(client, "dup@example.com")
    r = client.get("/me", headers=bearer(mint_token("dup@example.com", sub=uuid.uuid4())))
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"


def test_provisioning_race_rereads_the_winner(session_factory, monkeypatch):
    """Simulate a concurrent request inserting the row between our read and insert."""
    claims = local_verifier()(mint_token("race@example.com"))
    with session_factory() as s:
        winner = auth_svc.provision_user(s, claims)
        s.commit()
        real = auth_svc._by_auth_id
        calls = {"n": 0}

        def stale_first_read(session, auth_id):
            calls["n"] += 1
            return None if calls["n"] == 1 else real(session, auth_id)

        monkeypatch.setattr(auth_svc, "_by_auth_id", stale_first_read)
        monkeypatch.setattr(auth_svc, "select", _select_missing_email(auth_svc.select))
        assert auth_svc.provision_user(s, claims).id == winner.id
        assert calls["n"] == 2  # took the IntegrityError -> re-read path
        s.commit()
        assert s.query(User).count() == 1


def _select_missing_email(real_select):
    """`select(User).where(User.email == ...)` returns nothing on the first call, forcing the insert path."""
    state = {"first": True}

    def fake(*args, **kw):
        stmt = real_select(*args, **kw)
        if state["first"] and args and args[0] is User:
            state["first"] = False
            return stmt.where(User.id == -1)
        return stmt
    return fake


# ---------------------------------------------------------------- erasure
def _admin(handler) -> auth_svc.SupabaseAdmin:
    return auth_svc.SupabaseAdmin(TEST_SUPABASE_URL, "service-role-key", client=httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.fixture
def admin_calls():
    return []


def _app_with_admin(session_factory, tmp_path, llm, handler):
    a = create_app(session_factory, storage=LocalStorage(tmp_path / "uploads"), token_verifier=local_verifier(),
                   auth_admin=_admin(handler))
    a.state.provider_factory = lambda user_id, run_id: llm
    return TestClient(a)


def test_delete_me_calls_admin_api_and_blocks_old_token(session_factory, tmp_path, llm, admin_calls):
    def handler(req: httpx.Request):
        admin_calls.append(req)
        return httpx.Response(200, json={})

    c = _app_with_admin(session_factory, tmp_path, llm, handler)
    h = signup(c, "gone@example.com")
    assert upload(c, h).status_code == 201
    assert c.delete("/me", headers=h).status_code == 204
    (req,) = admin_calls
    assert req.method == "DELETE"
    assert str(req.url) == f"{TEST_SUPABASE_URL}/auth/v1/admin/users/{auth_id_for('gone@example.com')}"
    assert req.headers["authorization"] == "Bearer service-role-key" and req.headers["apikey"] == "service-role-key"
    # The still-unexpired access token cannot resurrect the account.
    assert c.get("/me", headers=h).status_code == 401
    with session_factory() as s:
        assert s.query(User).count() == 0 and s.query(ResumeVersion).count() == 0
        assert s.get(ErasedAccount, auth_id_for("gone@example.com")) is not None


def test_delete_me_tolerates_already_deleted_auth_user(session_factory, tmp_path, llm):
    c = _app_with_admin(session_factory, tmp_path, llm, lambda req: httpx.Response(404, json={"msg": "User not found"}))
    h = signup(c)
    assert c.delete("/me", headers=h).status_code == 204


def test_delete_me_admin_failure_is_502_and_retryable(session_factory, tmp_path, llm):
    responses = iter([httpx.Response(500), httpx.Response(200, json={})])
    c = _app_with_admin(session_factory, tmp_path, llm, lambda req: next(responses))
    h = signup(c)
    r = c.delete("/me", headers=h)
    assert r.status_code == 502 and r.json()["error"]["code"] == "upstream_error"
    with session_factory() as s:
        assert s.query(User).count() == 1  # rolled back: retry redoes the whole erasure
    assert c.delete("/me", headers=h).status_code == 204
    with session_factory() as s:
        assert s.query(User).count() == 0


def test_admin_from_env(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    assert auth_svc.SupabaseAdmin.from_env() is None
    monkeypatch.setenv("SUPABASE_URL", TEST_SUPABASE_URL)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    assert auth_svc.SupabaseAdmin.from_env() is None
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "k")
    assert auth_svc.SupabaseAdmin.from_env() is not None


# ---------------------------------------------------------------- storage
class FakeBucket:
    """Minimal in-memory Supabase Storage REST API."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.requests: list[httpx.Request] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.requests.append(req)
        assert req.headers["authorization"] == "Bearer srk" and req.headers["apikey"] == "srk"
        path = req.url.path
        if req.method == "POST" and path.startswith("/storage/v1/object/list/resumes"):
            body = json.loads(req.content)
            prefix, limit, offset = body["prefix"], body["limit"], body["offset"]
            names = sorted(k[len(prefix):] for k in self.objects if k.startswith(prefix))
            return httpx.Response(200, json=[{"name": n, "id": str(uuid.uuid4())} for n in names[offset:offset + limit]])
        if path.startswith("/storage/v1/object/resumes/"):
            key = path.removeprefix("/storage/v1/object/resumes/")
            if req.method == "POST":
                assert req.headers["x-upsert"] == "false"
                if key in self.objects:
                    return httpx.Response(409, json={"error": "Duplicate"})
                self.objects[key] = req.content
                return httpx.Response(200, json={"Key": f"resumes/{key}"})
            if req.method == "GET":
                return httpx.Response(200, content=self.objects[key]) if key in self.objects else httpx.Response(404)
        if req.method == "DELETE" and path == "/storage/v1/object/resumes":
            for k in json.loads(req.content)["prefixes"]:
                self.objects.pop(k, None)
            return httpx.Response(200, json=[])
        return httpx.Response(400, json={"error": f"unexpected {req.method} {path}"})


def _storage(bucket: FakeBucket) -> SupabaseStorage:
    return SupabaseStorage(TEST_SUPABASE_URL, "srk", client=httpx.Client(transport=httpx.MockTransport(bucket)))


def test_supabase_storage_roundtrip_and_user_erasure():
    bucket = FakeBucket()
    st = _storage(bucket)
    k1, k2 = st.save(7, "abc.pdf", b"one"), st.save(7, "abc.pdf", b"two")
    other = st.save(70, "x.txt", b"keep")
    assert k1 != k2 and k1.startswith("7/") and k1.endswith("-abc.pdf")
    assert st.load(k1) == b"one" and st.load(k2) == b"two"
    st.PAGE = 1  # exercise pagination
    st.delete_user(7)
    assert set(bucket.objects) == {other}
    lists = [json.loads(r.content) for r in bucket.requests if "/object/list/" in r.url.path]
    assert all(b["prefix"] == "7/" for b in lists)


def test_supabase_storage_errors_and_key_validation():
    st = _storage(FakeBucket())
    with pytest.raises(StorageError):
        st.load("7/missing.txt")
    for bad in ("../etc/passwd", "/abs", "7/../8/x"):
        with pytest.raises(ValueError):
            st.load(bad)
    down = SupabaseStorage(TEST_SUPABASE_URL, "srk", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))))
    with pytest.raises(StorageError):
        down.save(1, "a.txt", b"x")


def test_upload_through_api_lands_in_bucket_and_storage_outage_is_502(session_factory, llm):
    bucket = FakeBucket()
    a = create_app(session_factory, storage=_storage(bucket), token_verifier=local_verifier())
    a.state.provider_factory = lambda user_id, run_id: llm
    c = TestClient(a)
    h = signup(c)
    assert upload(c, h).status_code == 201
    (key,) = bucket.objects
    with session_factory() as s:
        assert s.query(ResumeVersion).one().storage_key == key
    assert c.delete("/me", headers=h).status_code == 204 and bucket.objects == {}

    a.state.storage = SupabaseStorage(TEST_SUPABASE_URL, "srk", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    h2 = signup(c, "b@example.com")
    r = upload(c, h2)
    assert r.status_code == 502 and r.json()["error"]["code"] == "storage_error"


def test_storage_chosen_from_env(monkeypatch, session_factory):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    assert isinstance(create_app(session_factory, token_verifier=local_verifier()).state.storage, LocalStorage)
    monkeypatch.setenv("SUPABASE_URL", TEST_SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "srk")
    app = create_app(session_factory)
    assert isinstance(app.state.storage, SupabaseStorage) and app.state.storage.bucket == "resumes"
    assert isinstance(app.state.token_verifier, auth_svc.SupabaseVerifier)
    assert isinstance(app.state.auth_admin, auth_svc.SupabaseAdmin)


# ------------------------------------------------------------- db / migrations
@pytest.mark.parametrize("url, disabled", [
    ("postgresql://u:p@aws-0-ca.pooler.supabase.com:6543/postgres", True),
    ("postgresql://u:p@db.abc.supabase.co:5432/postgres?pgbouncer=true", True),
    ("postgresql://u:p@db.abc.supabase.co:5432/postgres", False),
])
def test_transaction_pooler_disables_prepared_statements(monkeypatch, url, disabled):
    seen = {}
    monkeypatch.setattr("jobai.product.db.session.create_engine", lambda u, **kw: seen.update(url=u, **kw))
    make_engine(url)
    assert (seen["connect_args"].get("prepare_threshold", "unset") is None) == disabled
    assert seen["url"].drivername == "postgresql+psycopg" and "pgbouncer" not in seen["url"].query


def _migration_modules():
    for path in sorted((ROOT / "migrations" / "versions").glob("*.py")):
        spec = importlib.util.spec_from_file_location(f"_mig_{path.stem}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod


def test_every_table_has_rls_enabled_by_some_migration():
    """Tripwire: Supabase exposes `public` through its Data API; a table without
    RLS is readable with the anon key. New tables need RLS in their migration."""
    covered = set()
    for mod in _migration_modules():
        covered |= set(getattr(mod, "RLS_TABLES", ()))
    missing = set(Base.metadata.tables) - covered
    assert not missing, f"enable RLS for {sorted(missing)} in a migration's RLS_TABLES"
    assert "alembic_version" in covered
