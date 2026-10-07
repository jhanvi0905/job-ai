"""Multi-tenant schema.

Two ownership classes:
  * SHARED  — `jobs` is the global catalog, fetched once for everyone.
  * PER-USER — everything else carries `user_id`; every query in a service or
    router MUST filter on it (there is no row-level security in SQLite).

Verdicts are cached per (user, job) and invalidated by `rules_sig` (profile +
prefs + prompt/model signature) or `jd_hash` changing — the SaaS version of
the single-tenant DecisionCache.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    # Supabase auth.users.id (JWT `sub`). Null only for rows created before Supabase Auth.
    auth_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))  # legacy (pre-Supabase); unused
    plan: Mapped[str] = mapped_column(String(16), default="free")  # free | pro
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # erasure request marker
    # Last authenticated request (written at most hourly); drives the worker's daily refresh.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class SearchPrefs(Base):
    """One row per user. `data` is a product.services.prefs.SearchPrefsModel dump
    (countries, workplace types, role families, seniority, years, recency)."""
    __tablename__ = "search_prefs"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Job(Base):
    """SHARED catalog row (normalized posting)."""
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    content_key: Mapped[str] = mapped_column(String(64), index=True)  # company+title, cross-source dedup
    source: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(128))
    company: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(300))
    location: Mapped[str | None] = mapped_column(String(300))
    workplace_type: Mapped[str | None] = mapped_column(String(16))
    apply_url: Mapped[str] = mapped_column(String(1000))
    description: Mapped[str] = mapped_column(Text)
    description_hash: Mapped[str] = mapped_column(String(64))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    normalized: Mapped[dict] = mapped_column(JSON, default=dict)  # full NormalizedJob dump


class UserJobEvaluation(Base):
    """Per-user terminal disposition for a job. Exactly one row per (user, job);
    conservation: every job a run considered ends with a non-null `disposition`."""
    __tablename__ = "user_job_evaluations"
    __table_args__ = (UniqueConstraint("user_id", "job_id"), Index("ix_eval_user_fit", "user_id", "fit_rank"))
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    # filtered | rejected | triaged | matched | deferred | errored
    disposition: Mapped[str] = mapped_column(String(16))
    reason_code: Mapped[str | None] = mapped_column(String(64))
    classification: Mapped[dict | None] = mapped_column(JSON)  # JobClassification dump
    match: Mapped[dict | None] = mapped_column(JSON)           # JobMatch dump (stage 3)
    fit: Mapped[str | None] = mapped_column(String(16))        # no|weak|plausible|strong
    fit_rank: Mapped[int] = mapped_column(Integer, default=0)  # sortable form of fit
    jd_hash: Mapped[str] = mapped_column(String(64))
    rules_sig: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class ResumeVersion(Base):
    __tablename__ = "resume_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(500))  # object-storage / local path; never in git
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Achievement(Base):
    """Structured evidence bank row — same shape as data/achievements_index.yaml
    entries so jobai.engine.achievements.retrieval scores them unchanged."""
    __tablename__ = "achievements"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    resume_id: Mapped[int | None] = mapped_column(ForeignKey("resume_versions.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str] = mapped_column(Text, default="")
    fields: Mapped[dict] = mapped_column(JSON, default=dict)  # role_families, skills, system_patterns, *_signals
    user_edited: Mapped[bool] = mapped_column(Boolean, default=False)


class TailorRun(Base):
    __tablename__ = "tailor_runs"
    __table_args__ = (UniqueConstraint("user_id", "input_hash"),)  # cache key: resume_hash+jd_hash+prompt/model
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    resume_id: Mapped[int] = mapped_column(ForeignKey("resume_versions.id", ondelete="CASCADE"))
    input_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="proposed")  # proposed | accepted | failed
    proposal: Mapped[dict] = mapped_column(JSON, default=dict)  # [{original, proposed, evidence_ids}]
    accepted: Mapped[dict | None] = mapped_column(JSON)       # the user-approved subset
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("user_id", "job_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="saved")  # saved|tailored|applied|interview|offer|rejected
    notes: Mapped[str] = mapped_column(Text, default="")
    applied_on: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class LLMCall(Base):
    """Tenant-scoped replacement of the single-tenant ledger's llm_calls."""
    __tablename__ = "llm_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)  # null = system
    run_id: Mapped[str | None] = mapped_column(String(64), index=True)
    node: Mapped[str] = mapped_column(String(32))
    item_id: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(64))
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    outcome: Mapped[str] = mapped_column(String(24))  # ok | budget_exceeded | schema_error | ...
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class UsageCounter(Base):
    """Per-user per-day action counts powering plan caps."""
    __tablename__ = "usage_counters"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), primary_key=True)  # triage|deep_match|tailor|resume_parse
    count: Mapped[int] = mapped_column(Integer, default=0)


class CreditLedger(Base):
    """Append-only; balance = SUM(delta). Purchases +N, tailor overage -1."""
    __tablename__ = "credit_ledger"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(32))
    ref: Mapped[str | None] = mapped_column(String(128))  # e.g. payment-provider event id (idempotency)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class WaitlistEntry(Base):
    __tablename__ = "waitlist"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    source: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ErasedAccount(Base):
    """Tombstone of erased Supabase identities. An access token outlives the
    account it was issued for (stateless JWT, ~1h), so without this a request
    made right after `DELETE /me` would silently re-provision an empty user.
    Holds only the random auth id: no email, no profile data."""
    __tablename__ = "erased_accounts"
    auth_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    erased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Task(Base):
    """Background job queue row (services/tasks.py, scripts/product/run_worker.py).

    `dedupe_key` is set only while a deduplicated task is active (queued/running)
    and cleared when it finishes; the unique index therefore allows at most one
    active task per key (NULLs never collide). `payload`/`result` hold ids and
    counters only — never resume or job-description text."""
    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_claim", "status", "run_after"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)  # null = system
    kind: Mapped[str] = mapped_column(String(32))  # feed_refresh | resume_parse | catalog_ingest
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued | running | succeeded | failed
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    dedupe_key: Mapped[str | None] = mapped_column(String(96), unique=True)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RateLimitCounter(Base):
    """Fixed-window request counters (services/ratelimit.py). `key` is
    '{scope}:{subject}' where subject is a user id or client IP; rows older than
    a day are pruned by the worker."""
    __tablename__ = "rate_limits"
    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


class WorkerHeartbeat(Base):
    """One row per worker process, refreshed every loop; /ready reports the freshest."""
    __tablename__ = "worker_heartbeats"
    worker_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    version: Mapped[str | None] = mapped_column(String(64))
