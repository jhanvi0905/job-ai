"""Postgres-backed background task queue (no Redis).

Lifecycle: queued -> running -> succeeded | failed, with bounded retries:
a retryable failure goes back to `queued` with `run_after` pushed out by
exponential backoff until `max_attempts` is reached.

* enqueue  — feed_refresh is deduplicated per user and catalog_ingest globally:
             while one is queued/running, enqueue returns it instead of adding
             another (`dedupe_key` + unique index, so concurrent requests can't
             both insert).
* claim    — `SELECT ... FOR UPDATE SKIP LOCKED` on Postgres, so N workers never
             pick the same row; then a conditional UPDATE (status='queued') that is
             also what keeps the SQLite fallback (tests, local dev) correct. The
             row lock is held only for the claim transaction, never while the task
             runs (the Supabase transaction pooler would not like hour-long txns).
* reap     — a `running` task whose lock is older than LOCK_TIMEOUT (worker died
             mid-task) is requeued, or failed if out of attempts.

Payloads and results carry ids and counters only — never resume/JD text.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from jobai.product.db.models import RateLimitCounter, Task

log = logging.getLogger(__name__)

KINDS = ("feed_refresh", "resume_parse", "catalog_ingest")
ACTIVE = ("queued", "running")
TERMINAL = ("succeeded", "failed")
DEFAULT_MAX_ATTEMPTS = {"feed_refresh": 3, "resume_parse": 3, "catalog_ingest": 2}
BACKOFF_BASE_S = 30
BACKOFF_MAX_S = 30 * 60
LOCK_TIMEOUT = timedelta(minutes=20)  # longest legit task (a big feed refresh) must finish well inside this


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes even for timezone=True columns."""
    return dt.replace(tzinfo=UTC) if dt is not None and dt.tzinfo is None else dt


def dedupe_key(kind: str, user_id: int | None) -> str | None:
    if kind == "feed_refresh":
        return f"feed_refresh:{user_id}"
    if kind == "catalog_ingest":
        return "catalog_ingest"
    return None


def enqueue(session: Session, kind: str, user_id: int | None = None, payload: dict | None = None,
            run_after: datetime | None = None) -> tuple[Task, bool]:
    """Returns (task, created). Flushes but does not commit (caller's transaction)."""
    if kind not in KINDS:
        raise ValueError(f"unknown task kind: {kind}")
    key = dedupe_key(kind, user_id)
    if key is not None:
        existing = session.scalar(select(Task).where(Task.dedupe_key == key))
        if existing is not None:
            return existing, False
    task = Task(id=uuid.uuid4(), kind=kind, user_id=user_id, payload=dict(payload or {}), status="queued",
                attempts=0, max_attempts=DEFAULT_MAX_ATTEMPTS[kind], dedupe_key=key, run_after=run_after or _now(),
                created_at=_now())
    try:
        with session.begin_nested():
            session.add(task)
    except IntegrityError:  # lost a race with a concurrent enqueue of the same key
        existing = session.scalar(select(Task).where(Task.dedupe_key == key))
        if existing is None:
            raise
        return existing, False
    log.info("task enqueued", extra={"task_id": str(task.id), "kind": kind})
    return task, True


def get_for_user(session: Session, task_id: uuid.UUID, user_id: int) -> Task | None:
    return session.scalar(select(Task).where(Task.id == task_id, Task.user_id == user_id))


def active_count(session: Session, user_id: int, kind: str) -> int:
    return int(session.scalar(select(func.count()).select_from(Task).where(
        Task.user_id == user_id, Task.kind == kind, Task.status.in_(ACTIVE))) or 0)


def claim(session: Session, worker_id: str, kinds: tuple[str, ...] = KINDS, now: datetime | None = None) -> Task | None:
    """Lock and mark the next due task as running, then COMMIT. None if idle."""
    now = now or _now()
    candidate = session.scalar(
        select(Task).where(Task.status == "queued", Task.run_after <= now, Task.kind.in_(kinds))
        .order_by(Task.run_after, Task.created_at).limit(1)
        .with_for_update(skip_locked=True)  # ignored by SQLite; the conditional UPDATE below covers it
    )
    if candidate is None:
        session.rollback()
        return None
    result = session.execute(
        update(Task).where(Task.id == candidate.id, Task.status == "queued")
        .values(status="running", locked_at=now, locked_by=worker_id[:128], attempts=Task.attempts + 1)
        .execution_options(synchronize_session=False)
    )
    session.commit()
    if result.rowcount != 1:
        return None  # someone else got it (SQLite path only)
    session.refresh(candidate)
    return candidate


def backoff(attempt: int) -> timedelta:
    return timedelta(seconds=min(BACKOFF_MAX_S, BACKOFF_BASE_S * 2 ** max(0, attempt - 1)))


def complete(session: Session, task_id: uuid.UUID, result: dict[str, Any]) -> None:
    session.execute(update(Task).where(Task.id == task_id).values(
        status="succeeded", result=result, error=None, finished_at=_now(), locked_at=None, dedupe_key=None))
    session.commit()


def fail(session: Session, task_id: uuid.UUID, error: str, *, retryable: bool = True) -> str:
    """Requeue with backoff while attempts remain (and the error is retryable),
    else mark failed. Returns the new status."""
    task = session.get(Task, task_id)
    if task is None:  # e.g. the user erased their account mid-task
        session.rollback()
        return "failed"
    if retryable and task.attempts < task.max_attempts:
        task.status, task.run_after = "queued", _now() + backoff(task.attempts)
        task.locked_at = task.locked_by = None
        task.error = error[:500]
    else:
        task.status, task.finished_at, task.dedupe_key = "failed", _now(), None
        task.locked_at = None
        task.error = error[:500]
    status = task.status
    session.commit()
    return status


def release(session: Session, task_id: uuid.UUID) -> None:
    """Put a task we were interrupted on straight back (shutdown); the attempt is not counted."""
    task = session.get(Task, task_id)
    if task is not None and task.status == "running":
        task.status, task.locked_at, task.locked_by = "queued", None, None
        task.attempts = max(0, task.attempts - 1)
        task.run_after = _now()
    session.commit()


def reap_stale(session: Session, now: datetime | None = None, lock_timeout: timedelta = LOCK_TIMEOUT) -> int:
    """Recover tasks whose worker vanished. Returns how many were touched."""
    now = now or _now()
    stale = list(session.scalars(
        select(Task).where(Task.status == "running", Task.locked_at < now - lock_timeout).with_for_update(skip_locked=True)))
    for task in stale:
        if task.attempts < task.max_attempts:
            task.status, task.run_after = "queued", now
        else:
            task.status, task.finished_at, task.dedupe_key = "failed", now, None
        task.locked_at = task.locked_by = None
        task.error = "worker lost while running (lock expired)"
        log.warning("reaped stale task", extra={"task_id": str(task.id), "kind": task.kind, "new_status": task.status})
    session.commit()
    return len(stale)


def last_created(session: Session, kind: str, user_id: int | None = None) -> datetime | None:
    q = select(func.max(Task.created_at)).where(Task.kind == kind)
    if user_id is not None:
        q = q.where(Task.user_id == user_id)
    return _aware(session.scalar(q))


def prune(session: Session, now: datetime | None = None, keep_days: int = 30) -> None:
    """Housekeeping: drop finished tasks after `keep_days` and rate-limit windows after a day."""
    now = now or _now()
    session.execute(delete(Task).where(Task.status.in_(TERMINAL), Task.finished_at < now - timedelta(days=keep_days)))
    session.execute(delete(RateLimitCounter).where(RateLimitCounter.window_start < now - timedelta(days=1)))
    session.commit()


def to_dict(task: Task) -> dict[str, Any]:
    """The public shape of GET /tasks/{id}."""
    return {
        "id": str(task.id), "kind": task.kind, "status": task.status, "result": task.result,
        "error": task.error if task.status == "failed" else None,
        "created_at": _aware(task.created_at), "finished_at": _aware(task.finished_at),
    }
