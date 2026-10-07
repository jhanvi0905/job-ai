"""Background worker: runs queued tasks (services/tasks.py) and schedules the
recurring ones. Entry point: scripts/product/run_worker.py. Tests drive it with
`run_until_idle` (synchronous, same code path as production).

Handlers
  feed_refresh   evaluate_for_user(...)      result = EvalSummary as a dict
  resume_parse   parse_resume(...)           result = {"achievements": <bank size>}
  catalog_ingest ingest_catalog(...)         result = IngestSummary as a dict

Errors stored on a task are short codes safe to show the user; the exception
itself goes to the log/Sentry (ids only, never resume/JD text).

Scheduler (every SCHEDULE_EVERY_S, any number of workers can run it — the
dedupe key keeps it to one active task per kind/user):
  * catalog_ingest every CATALOG_INGEST_INTERVAL_MIN (default 360);
  * one feed_refresh per day for users seen in the last ACTIVE_USER_DAYS (14) who
    still have triage quota today and have no refresh in the last 24h.
"""
from __future__ import annotations

import dataclasses
import logging
import os
import socket
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from jobai.engine.ai.provider import BudgetExceeded, LLMError
from jobai.product import observability
from jobai.product.db.models import ResumeVersion, Task, User, WorkerHeartbeat
from jobai.product.services import quota
from jobai.product.services import tasks as tasks_svc
from jobai.product.services.quota import QuotaExceeded
from jobai.product.services.resume import ResumeError, StorageError

log = logging.getLogger(__name__)

ProviderFactory = Callable[[int, str], Any]
ACTIVE_USER_DAYS = 14
DAILY_REFRESH_EVERY = timedelta(hours=24)
SCHEDULE_EVERY_S = 300
HEARTBEAT_EVERY_S = 30
HEARTBEAT_LOG_EVERY_S = 600
PRUNE_EVERY_S = 3600


class NonRetryable(Exception):
    """A failure retrying cannot fix; `code` is what the user sees."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _as_dict(summary: Any) -> dict:
    if hasattr(summary, "model_dump"):
        return summary.model_dump(mode="json")
    if dataclasses.is_dataclass(summary):
        return dataclasses.asdict(summary)
    return dict(summary)


def default_provider_factory(session_factory: sessionmaker[Session]) -> ProviderFactory:
    def make(user_id: int, run_id: str):
        from jobai.product.services.llm import make_user_provider

        return make_user_provider(session_factory, user_id, run_id)
    return make


# ------------------------------------------------------------------ handlers
def _feed_refresh(session_factory, task: Task, provider_factory: ProviderFactory) -> dict:
    from jobai.product.services.evaluation import evaluate_for_user

    run_id = f"feed-{task.id.hex[:12]}"
    with session_factory() as session:
        if session.get(User, task.user_id) is None:
            raise NonRetryable("user_not_found")
        summary = evaluate_for_user(session, task.user_id, provider_factory(task.user_id, run_id),
                                    max_jobs=task.payload.get("max_jobs"), run_id=run_id)
        session.commit()
    return _as_dict(summary)


def _resume_parse(session_factory, task: Task, provider_factory: ProviderFactory) -> dict:
    from jobai.product.services.resume import parse_resume

    with session_factory() as session:
        row = session.scalar(select(ResumeVersion).where(
            ResumeVersion.id == task.payload.get("resume_id"), ResumeVersion.user_id == task.user_id))
        if row is None:
            raise NonRetryable("resume_not_found")
        bank = parse_resume(session, task.user_id, row, provider_factory(task.user_id, f"parse-{task.id.hex[:12]}"))
        session.commit()
        return {"achievements": len(bank)}


def _catalog_ingest(session_factory, task: Task, _provider_factory: ProviderFactory) -> dict:
    from jobai.product.services.catalog import ingest_catalog

    with session_factory() as session:
        summary = ingest_catalog(session)
        session.commit()
    return _as_dict(summary)


HANDLERS: dict[str, Callable[..., dict]] = {
    "feed_refresh": _feed_refresh,
    "resume_parse": _resume_parse,
    "catalog_ingest": _catalog_ingest,
}


def classify_error(exc: Exception) -> tuple[str, bool]:
    """(user-safe error code, retryable)."""
    if isinstance(exc, NonRetryable):
        return exc.code, False
    if isinstance(exc, QuotaExceeded):
        return f"quota_exceeded: daily {exc.kind} limit reached ({exc.limit})", False
    if isinstance(exc, BudgetExceeded):
        return "budget_exceeded: model budget reached; try again later", False
    if isinstance(exc, ResumeError):
        return f"invalid_resume: {exc}"[:200], False
    if isinstance(exc, LookupError):
        return "not_found", False
    if isinstance(exc, LLMError):
        return f"llm_error: {exc.outcome}", True
    if isinstance(exc, StorageError):
        return "storage_error", True
    if isinstance(exc, OperationalError):
        return "database_error", True
    return "internal_error", True


def execute(session_factory: sessionmaker[Session], task: Task, provider_factory: ProviderFactory) -> str:
    """Run one claimed task to a terminal or requeued state. Returns the new status."""
    token = observability.new_context(request_id=f"task-{task.id.hex[:12]}", user_id=task.user_id, task_kind=task.kind)
    started = time.perf_counter()
    try:
        try:
            result = HANDLERS[task.kind](session_factory, task, provider_factory)
        except Exception as exc:  # noqa: BLE001 — classified below; one bad task never kills the worker
            code, retryable = classify_error(exc)
            level = logging.ERROR if code in ("internal_error", "database_error") else logging.WARNING
            log.log(level, "task failed", exc_info=level == logging.ERROR, extra={
                "task_id": str(task.id), "kind": task.kind, "attempt": task.attempts, "error_code": code.split(":")[0],
                "exc_type": type(exc).__name__})
            with session_factory() as s:
                return tasks_svc.fail(s, task.id, code, retryable=retryable)
        with session_factory() as s:
            tasks_svc.complete(s, task.id, result)
        log.info("task succeeded", extra={"task_id": str(task.id), "kind": task.kind,
                                          "duration_ms": round((time.perf_counter() - started) * 1000)})
        return "succeeded"
    finally:
        observability.reset_context(token)


def run_once(session_factory: sessionmaker[Session], provider_factory: ProviderFactory, worker_id: str) -> Task | None:
    with session_factory() as s:
        task = tasks_svc.claim(s, worker_id)
    if task is not None:
        execute(session_factory, task, provider_factory)
    return task


def run_until_idle(session_factory: sessionmaker[Session], provider_factory: ProviderFactory | None = None,
                   worker_id: str = "inline", max_tasks: int = 100) -> int:
    """Drain every due task synchronously (tests, local scripts). Returns tasks run."""
    provider_factory = provider_factory or default_provider_factory(session_factory)
    n = 0
    while n < max_tasks and run_once(session_factory, provider_factory, worker_id) is not None:
        n += 1
    return n


# ----------------------------------------------------------------- scheduler
def schedule(session_factory: sessionmaker[Session], now: datetime | None = None,
             ingest_interval: timedelta | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    if ingest_interval is None:
        ingest_interval = timedelta(minutes=int(os.environ.get("CATALOG_INGEST_INTERVAL_MIN", "360")))
    out = {"catalog_ingest": 0, "feed_refresh": 0}
    with session_factory() as s:
        last = tasks_svc.last_created(s, "catalog_ingest")
        if last is None or now - last >= ingest_interval:
            _, created = tasks_svc.enqueue(s, "catalog_ingest")
            out["catalog_ingest"] += int(created)
        users = s.scalars(select(User).where(User.deleted_at.is_(None),
                                             User.last_seen_at >= now - timedelta(days=ACTIVE_USER_DAYS))).all()
        for user in users:
            last = tasks_svc.last_created(s, "feed_refresh", user.id)
            if last is not None and now - last < DAILY_REFRESH_EVERY:
                continue
            if quota.remaining(s, user.id, "triage") <= 0:
                continue  # respect today's plan cap; tomorrow's pass will pick them up
            _, created = tasks_svc.enqueue(s, "feed_refresh", user_id=user.id, payload={"trigger": "scheduled"})
            out["feed_refresh"] += int(created)
        s.commit()
    if any(out.values()):
        log.info("scheduled tasks", extra=out)
    return out


def heartbeat(session_factory: sessionmaker[Session], worker_id: str, started_at: datetime) -> None:
    now = datetime.now(UTC)
    with session_factory() as s:
        row = s.get(WorkerHeartbeat, worker_id)
        if row is None:
            s.add(WorkerHeartbeat(worker_id=worker_id, started_at=started_at, last_seen_at=now,
                                  version=(os.environ.get("GIT_SHA") or "")[:64] or None))
        else:
            row.last_seen_at = now
        s.query(WorkerHeartbeat).filter(WorkerHeartbeat.last_seen_at < now - timedelta(days=1)).delete()
        s.commit()


# --------------------------------------------------------------------- loop
class Worker:
    def __init__(self, session_factory: sessionmaker[Session], provider_factory: ProviderFactory | None = None,
                 poll_interval_s: float | None = None, schedule_enabled: bool = True):
        self.session_factory = session_factory
        self.provider_factory = provider_factory or default_provider_factory(session_factory)
        self.poll_interval_s = poll_interval_s if poll_interval_s is not None else float(os.environ.get("WORKER_POLL_INTERVAL_S", "2"))
        self.schedule_enabled = schedule_enabled
        self.worker_id = f"{os.environ.get('FLY_MACHINE_ID') or socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self.stop = threading.Event()
        self.started_at = datetime.now(UTC)
        self._last: dict[str, float] = {}
        self.current: Task | None = None

    def _due(self, name: str, every_s: float) -> bool:
        now = time.monotonic()
        if now - self._last.get(name, -1e18) >= every_s:
            self._last[name] = now
            return True
        return False

    def housekeeping(self) -> None:
        if self._due("heartbeat", HEARTBEAT_EVERY_S):
            heartbeat(self.session_factory, self.worker_id, self.started_at)
        if self._due("heartbeat_log", HEARTBEAT_LOG_EVERY_S):
            log.info("worker heartbeat", extra={"worker_id": self.worker_id})
        if self._due("reap", 60):
            with self.session_factory() as s:
                tasks_svc.reap_stale(s)
        if self.schedule_enabled and self._due("schedule", SCHEDULE_EVERY_S):
            schedule(self.session_factory)
        if self._due("prune", PRUNE_EVERY_S):
            with self.session_factory() as s:
                tasks_svc.prune(s)

    def run_forever(self) -> None:
        log.info("worker started", extra={"worker_id": self.worker_id})
        while not self.stop.is_set():
            try:
                self.housekeeping()
                with self.session_factory() as s:
                    task = tasks_svc.claim(s, self.worker_id)
                if task is None:
                    self.stop.wait(self.poll_interval_s)
                    continue
                self.current = task
                try:
                    execute(self.session_factory, task, self.provider_factory)
                finally:
                    self.current = None
            except KeyboardInterrupt:  # second signal: abandon the current task, hand it back
                if self.current is not None:
                    with self.session_factory() as s:
                        tasks_svc.release(s, self.current.id)
                    log.warning("released task on forced shutdown", extra={"task_id": str(self.current.id)})
                break
            except Exception:  # noqa: BLE001 — DB blip etc.: log, back off, keep serving
                log.exception("worker loop error")
                self.stop.wait(min(30.0, self.poll_interval_s * 5))
        log.info("worker stopped", extra={"worker_id": self.worker_id})
