#!/usr/bin/env python3
"""Entrypoint for the local dashboard API server (control panel backend).

    python scripts/assistant/run_dashboard_api.py            # serve on 127.0.0.1:8000

Ops-only: not deployed by fly.toml. Every route requires `Authorization: Bearer
$ADMIN_TOKEN`; with ADMIN_TOKEN unset it serves loopback clients only (dev) or
refuses to start (any other APP_ENV). Never bind it to a public interface.
"""


import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("jobai.assistant.dashboard_api.app:app", host="127.0.0.1", port=8000, reload=False)
