"""Multi-tenant product API (separate from the single-tenant admin app in
src/jobai/assistant/dashboard_api). `create_app(session_factory)` takes the factory so tests
run on an in-memory/temp SQLite without touching env or disk.

Everything else defaults from the environment and can be injected:
  * token_verifier — Supabase JWT verifier (SUPABASE_URL [+ SUPABASE_JWT_SECRET]);
  * storage        — Supabase Storage (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY) else local disk;
  * auth_admin     — Supabase Auth Admin client used by DELETE /me (same two vars), else skipped.

Production hardening lives here: JSON logs with request ids, Sentry (SENTRY_DSN),
security headers, strict CORS (CORS_ORIGINS; no wildcard outside dev), a global
request-body cap, and no /docs or /openapi.json when APP_ENV=prod. LLM-heavy work
(feed refresh, resume parsing) is queued for scripts/product/run_worker.py, never run in
the request."""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from jobai.product import observability
from jobai.product.api.errors import install_error_handlers
from jobai.product.api.middleware import BodySizeLimitMiddleware, RequestContextMiddleware, SecurityHeadersMiddleware
from jobai.product.api.routers import (
    applications,
    auth,
    billing,
    feed,
    health,
    jobs,
    prefs,
    resume,
    tailor,
    tasks,
    usage,
    waitlist,
)
from jobai.product.db.session import make_engine, make_session_factory
from jobai.product.services.auth import SupabaseAdmin, check_auth_config, is_dev, is_prod, verifier_from_env
from jobai.product.services.resume import storage_from_env

log = logging.getLogger(__name__)

CORS_HEADERS = ["Authorization", "Content-Type", "X-Request-ID"]


def cors_origins() -> list[str]:
    origins = [o.strip().rstrip("/") for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
    if not is_dev():
        if not origins or "*" in origins:
            raise RuntimeError("CORS_ORIGINS must list explicit origins (no '*') when APP_ENV is not dev")
        insecure = [o for o in origins if not o.startswith("https://")]
        if is_prod() and insecure:
            raise RuntimeError(f"CORS_ORIGINS must be https in prod: {insecure}")
    return origins


def create_app(session_factory=None, storage=None, token_verifier=None, auth_admin=None) -> FastAPI:
    observability.configure_logging("api")
    observability.init_sentry("api")
    token_verifier = token_verifier or verifier_from_env()
    check_auth_config(token_verifier)
    if session_factory is None:
        session_factory = make_session_factory(make_engine())
    prod = is_prod()
    app = FastAPI(title="Job Match API", docs_url=None if prod else "/docs", redoc_url=None if prod else "/redoc",
                  openapi_url=None if prod else "/openapi.json")
    app.state.session_factory = session_factory
    app.state.storage = storage or storage_from_env()
    app.state.token_verifier = token_verifier
    app.state.auth_admin = auth_admin or SupabaseAdmin.from_env()

    # add_middleware prepends: the LAST added is the outermost. Order, outside in:
    # request context -> security headers -> CORS -> body limit -> app.
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=cors_origins(), allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                       allow_headers=CORS_HEADERS, expose_headers=["X-Request-ID", "Retry-After"], max_age=600)
    app.add_middleware(SecurityHeadersMiddleware, hsts=not is_dev())
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)
    for module in (health, auth, waitlist, prefs, resume, feed, jobs, tailor, tasks, applications, usage, billing):
        app.include_router(module.router)
    log.info("api configured", extra={"app_env": os.environ.get("APP_ENV", "dev"), "release": os.environ.get("GIT_SHA")})
    return app
