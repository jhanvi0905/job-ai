"""Ops dashboard API (single-tenant control panel: config files, ledger runs,
manual pipeline triggers). It is NOT part of the public product and is NOT
deployed by fly.toml; run it locally (scripts/assistant/run_dashboard_api.py, bound to
127.0.0.1) or behind a private network only.

Auth: every route requires `Authorization: Bearer $ADMIN_TOKEN`
(constant-time compare). If ADMIN_TOKEN is unset:
  * APP_ENV=dev  — only loopback clients are served (local dashboard keeps working);
  * otherwise    — the app refuses to start.
"""
from __future__ import annotations

import hmac
import logging
import os

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from jobai.assistant.dashboard_api.routers import config as config_router
from jobai.assistant.dashboard_api.routers import runs as runs_router

log = logging.getLogger(__name__)
LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


def _is_dev() -> bool:
    return os.environ.get("APP_ENV", "dev").strip().lower() in ("dev", "development", "test")


def check_admin_config() -> None:
    if os.environ.get("ADMIN_TOKEN"):
        return
    if not _is_dev():
        raise RuntimeError("ADMIN_TOKEN must be set to run the dashboard API outside APP_ENV=dev")
    log.warning("ADMIN_TOKEN unset: dashboard API serves loopback clients only")


def require_admin(request: Request) -> None:
    token = os.environ.get("ADMIN_TOKEN", "")
    if not token:
        host = request.client.host if request.client else ""
        if _is_dev() and host in LOOPBACK:
            return
        raise HTTPException(401, "admin token required", headers={"WWW-Authenticate": "Bearer"})
    scheme, _, given = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(given.strip().encode(), token.encode()):
        raise HTTPException(401, "admin token required", headers={"WWW-Authenticate": "Bearer"})


def create_app() -> FastAPI:
    check_admin_config()
    dev = _is_dev()
    application = FastAPI(title="LifeOS Job Agent Dashboard API", dependencies=[Depends(require_admin)],
                          docs_url="/docs" if dev else None, redoc_url=None, openapi_url="/openapi.json" if dev else None)
    origins = [o.strip() for o in os.environ.get("DASHBOARD_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    application.include_router(config_router.router, prefix="/api")
    application.include_router(runs_router.router, prefix="/api")

    @application.get("/api/health-check")
    def health_check() -> dict:
        """Liveness probe — distinct from the ledger-tripwire /api/health."""
        return {"status": "ok"}

    return application


app = create_app()
