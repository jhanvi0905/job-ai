"""Background worker for the product API: runs queued tasks (feed refresh,
resume parse, catalog ingest) and schedules the recurring ones.

    python scripts/product/run_worker.py

Env: DATABASE_URL, AIMLAPI_KEY, SUPABASE_* (as the API), APP_ENV, SENTRY_DSN,
GIT_SHA, CATALOG_INGEST_INTERVAL_MIN (default 360), WORKER_POLL_INTERVAL_S
(default 2), WORKER_SCHEDULE=0 to disable scheduling on this process.

Shutdown: the first SIGTERM/SIGINT stops claiming new work and lets the current
task finish (Fly's kill_timeout in fly.toml bounds this). A second signal
abandons the task and puts it straight back in the queue. If the process is
killed outright, the reaper requeues the task once its lock expires.
"""
from __future__ import annotations

import logging  # noqa: E402
import os  # noqa: E402
import signal  # noqa: E402

from jobai.product import observability  # noqa: E402
from jobai.product.db.session import make_engine, make_session_factory  # noqa: E402
from jobai.product.worker import Worker  # noqa: E402

log = logging.getLogger("product.worker")


def main() -> None:
    observability.configure_logging("worker")
    observability.init_sentry("worker")
    worker = Worker(make_session_factory(make_engine()),
                    schedule_enabled=os.environ.get("WORKER_SCHEDULE", "1") not in ("0", "false", "no"))

    def on_signal(signum, _frame):
        if worker.stop.is_set():
            raise KeyboardInterrupt  # second signal: abandon the current task (it is released, not lost)
        log.info("shutdown requested; finishing current task", extra={"signal": signal.Signals(signum).name})
        worker.stop.set()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    worker.run_forever()


if __name__ == "__main__":
    main()
