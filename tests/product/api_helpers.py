"""Shared fixtures for the product API tests (imported into test modules; no conftest.py).

Everything is offline: temp SQLite, LocalStorage in tmp_path, a FakeLLM whose
`_chat` mimics the gateway contract (runs `validate=`, returns parsed JSON), and
Supabase-shaped access tokens signed by a local EC key (no JWKS fetch)."""
from __future__ import annotations

import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from jobai.product.api.app import create_app
from jobai.product.db.models import Base, Job
from jobai.product.services.auth import SupabaseVerifier
from jobai.product.services.resume import LocalStorage

# ------------------------------------------------------------- test tokens
TEST_SUPABASE_URL = "https://test-project.supabase.co"
TEST_ISSUER = f"{TEST_SUPABASE_URL}/auth/v1"
TEST_KID = "test-key-1"
TEST_PRIVATE_KEY = ec.generate_private_key(ec.SECP256R1())  # once per test session
TEST_PUBLIC_KEY = TEST_PRIVATE_KEY.public_key()


def local_verifier(**kw) -> SupabaseVerifier:
    """The production verifier with the JWKS lookup replaced by the local public key."""
    return SupabaseVerifier(TEST_SUPABASE_URL, key_resolver=lambda _token: TEST_PUBLIC_KEY, **kw)


def auth_id_for(email: str) -> uuid.UUID:
    """Stable fake Supabase user id per email, so repeated signup() calls are the same identity."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"supabase-test:{email.lower()}")


def mint_token(email: str = "a@example.com", sub: str | uuid.UUID | None = None, key=None, alg: str = "ES256",
               ttl: int = 3600, kid: str = TEST_KID, **overrides) -> str:
    now = int(time.time())
    claims = {"sub": str(sub or auth_id_for(email)), "email": email, "aud": "authenticated", "role": "authenticated",
              "iss": TEST_ISSUER, "iat": now, "exp": now + ttl, "is_anonymous": False, **overrides}
    return jwt.encode(claims, key or TEST_PRIVATE_KEY, algorithm=alg, headers={"kid": kid})


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class FakeLLM:
    """Canned response per workflow; counts calls. Honors `validate` like the gateway."""

    def __init__(self, by_workflow: dict):
        self.by = dict(by_workflow)
        self.calls: list[dict] = []

    def _chat(self, **kw):
        self.calls.append(kw)
        out = self.by[kw["workflow"]]
        if kw.get("validate"):
            kw["validate"](out)
        return out


PARSED = {"achievements": [
    {"title": "Built streaming pipeline", "summary": "Cut latency by 40% using Kafka.", "skills": ["kafka"],
     "role_families": ["data_engineering"]},
    {"title": "Led migration", "summary": "Moved 12 services to Kubernetes.", "skills": ["kubernetes"]},
]}


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def llm():
    return FakeLLM({"parse_resume": PARSED, "tailor_resume": {"bullets": []}})


@pytest.fixture
def app(session_factory, tmp_path, llm):
    a = create_app(session_factory, storage=LocalStorage(tmp_path / "uploads"), token_verifier=local_verifier())
    a.state.provider_factory = lambda user_id, run_id: llm
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def job(session_factory):
    with session_factory() as s:
        j = Job(fingerprint="fp1", content_key="ck1", source="t", external_id="1", company="Acme", title="Data Engineer",
                location="Remote", workplace_type="remote", apply_url="https://x/1", description="Build Kafka pipelines",
                description_hash="jdh1")
        s.add(j)
        s.commit()
        return j.id


def signup(client, email="a@example.com", password=None) -> dict:
    """What the browser does after Supabase sign-up: call the API with the access
    token. The first authenticated request provisions the user row."""
    headers = bearer(mint_token(email))
    r = client.get("/me", headers=headers)
    assert r.status_code == 200, r.text
    return headers


def drain(client) -> int:
    """Run every queued background task now, in-process (what scripts/product/run_worker.py
    does in production), using the app's injected provider factory."""
    from jobai.product.worker import run_until_idle

    state = client.app.state
    return run_until_idle(state.session_factory, getattr(state, "provider_factory", None))


def upload(client, headers, text=b"Experience: built a streaming pipeline with Kafka, cut latency by 40%.", run_tasks=True):
    """POST /resume, then (by default) run the queued parse so achievements exist."""
    r = client.post("/resume", headers=headers, files={"file": ("cv.txt", text, "text/plain")})
    if run_tasks and r.status_code == 201:
        drain(client)
    return r
