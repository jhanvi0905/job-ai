"""Launch the multi-tenant product API (port 8100). Env: DATABASE_URL, SUPABASE_URL,
SUPABASE_SERVICE_ROLE_KEY, APP_ENV, CORS_ORIGINS, UPLOAD_DIR, API_HOST, API_PORT, SENTRY_DSN.
Run `alembic upgrade head` first, and `python scripts/product/run_worker.py` alongside: feed
refreshes and resume parsing are queued for the worker, not run in the request."""
from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "jobai.product.api.app:create_app",
        factory=True,
        host=os.environ.get("API_HOST", "127.0.0.1"),
        port=int(os.environ.get("API_PORT", "8100")),
    )
