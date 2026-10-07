"""Shared fixtures for the multi-tenant product layer. In-memory SQLite, a
scripted provider, and no network (the root conftest still blocks HTTP)."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from jobai.engine.ai.provider import BudgetExceeded
from jobai.engine.jobs.fingerprint import compute_description_hash
from jobai.engine.jobs.schemas import NormalizedJob
from jobai.product.db.models import Achievement, Base, Job, User
from jobai.product.services.catalog import _apply  # noqa: PLC2701 — builds Job rows the same way ingest does


class FakeProvider:
    """Stands in for LLMProvider._chat. `script` maps workflow -> dict, or a
    callable(kwargs) -> dict, or an Exception to raise. Counts calls per workflow."""

    def __init__(self, classify=None, match=None):
        self.script = {
            "classify_job": classify if classify is not None else CLASSIFY_OK,
            "analyse_match": match if match is not None else MATCH_STRONG,
        }
        self.calls: dict[str, int] = {"classify_job": 0, "analyse_match": 0}

    @property
    def total_calls(self) -> int:
        return sum(self.calls.values())

    def _chat(self, **kw):
        wf = kw["workflow"]
        self.calls[wf] += 1
        item = self.script[wf]
        if callable(item):
            item = item(kw)
        if isinstance(item, Exception):
            raise item
        return dict(item)


CLASSIFY_OK = {"role_family": "RF02", "seniority": "senior", "role_type": "ai_ml_engineering", "fit": "strong",
               "min_years_required": None, "why": "good", "hard_blocker": False, "key_requirements": ["Python", "LLM"]}
CLASSIFY_NO = {**CLASSIFY_OK, "fit": "no", "why": "wrong role"}
MATCH_STRONG = {"requirements": [{"req": "Python", "evidence": "direct", "importance": "core", "achievement_ids": []}],
                "blocker": False, "reason": "great"}
MATCH_WEAK = {"requirements": [{"req": "Rust", "evidence": "none", "importance": "core", "achievement_ids": []}],
              "blocker": False, "reason": "no evidence"}
BUDGET_ERROR = BudgetExceeded("budget_exceeded", "per_day")


@pytest.fixture(autouse=True)
def _no_real_supabase(monkeypatch):
    """A developer's real Supabase env (shell or .env) must never reach a test:
    create_app() would otherwise build a live Storage/Admin client from it."""
    for var in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_JWT_SECRET", "SUPABASE_STORAGE_BUCKET"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def session(factory):
    with factory() as s:
        yield s


@pytest.fixture
def make_user(session):
    def _make(email: str, plan: str = "pro") -> User:
        user = User(email=email, password_hash="x", plan=plan)
        session.add(user)
        session.commit()
        return user
    return _make


@pytest.fixture
def make_job(session):
    counter = iter(range(1, 10_000))

    def _make(title="Senior ML Engineer", location="Remote", workplace="Remote",
              description="Build LLM and RAG systems in Python.", **kw) -> Job:
        i = next(counter)
        nj = NormalizedJob(
            external_job_id=str(i), source="greenhouse", source_company_identifier="acme", company_name=f"Acme{i}",
            title=title, location=location, workplace_type=workplace, description=description,
            job_url=f"https://x/{i}", application_url=f"https://x/{i}", job_fingerprint=f"greenhouse:{i}",
            description_hash=compute_description_hash(description), **kw,
        )
        row = Job(fingerprint=nj.job_fingerprint, active=True)
        _apply(row, nj)
        session.add(row)
        session.commit()
        return row
    return _make


@pytest.fixture
def add_achievement(session):
    def _add(user_id: int, title="Built RAG platform", **fields) -> Achievement:
        row = Achievement(user_id=user_id, title=title, summary="Shipped it.",
                          fields={"role_families": ["RF02"], "skills": ["Python", "RAG"], **fields})
        session.add(row)
        session.commit()
        return row
    return _add
