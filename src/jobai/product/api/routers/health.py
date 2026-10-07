"""Liveness (/health) and readiness (/ready).

/health never touches the database: Fly's routing check uses it, and a Supabase
blip must not take every machine out of rotation. /ready checks the database is
reachable and the schema is at the Alembic head (Fly's deploy-gating check and
the runbook's first command); the worker heartbeat is reported but not gating."""
from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from functools import lru_cache

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from jobai.core.paths import REPO_ROOT
from jobai.product.db.models import WorkerHeartbeat

log = logging.getLogger(__name__)
router = APIRouter()
ROOT = REPO_ROOT


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@lru_cache(maxsize=1)
def migration_heads() -> frozenset[str]:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return frozenset(ScriptDirectory.from_config(cfg).get_heads())


@router.get("/ready")
def ready(request: Request):
    checks: dict[str, object] = {}
    ok = True
    try:
        with request.app.state.session_factory() as s:
            s.execute(text("SELECT 1"))
            checks["database"] = "ok"
            try:
                current = set(s.scalars(text("SELECT version_num FROM alembic_version")))
            except SQLAlchemyError:
                s.rollback()
                current = set()
            heads = set(migration_heads())
            checks["migrations"] = "ok" if current == heads else f"at {sorted(current) or 'none'}, head {sorted(heads)}"
            ok = current == heads
            try:
                last = s.scalar(select(func.max(WorkerHeartbeat.last_seen_at)))
            except SQLAlchemyError:
                s.rollback()
                last = None
            if last is not None and last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            checks["worker_last_seen_s"] = None if last is None else round((datetime.now(UTC) - last).total_seconds())
    except SQLAlchemyError as exc:
        log.error("readiness: database unreachable: %s", type(exc).__name__)
        checks["database"] = "unreachable"
        ok = False
    body = {"status": "ready" if ok else "not_ready", "checks": checks, "release": os.environ.get("GIT_SHA")}
    return JSONResponse(body, status_code=200 if ok else 503)
