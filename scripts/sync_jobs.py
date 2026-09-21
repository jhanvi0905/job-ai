#!/usr/bin/env python3
"""Entrypoint for a pipeline run — what cron / GitHub Actions actually calls.
Loads .env for local runs; in CI, secrets come from the environment directly."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from src.telemetry.logging import configure_logging  # noqa: E402
from src.workflows.process_job import run  # noqa: E402

if __name__ == "__main__":
    configure_logging()
    summary = run()
    print(summary.as_text())
    if summary.source_errors:
        # Non-zero exit surfaces partial failures in CI logs without treating
        # a single dead source as fatal for the whole run (PRD §33).
        sys.exit(1)
