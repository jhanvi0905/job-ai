"""Read application emails (read-only) and advance Job Pipeline statuses.

    python scripts/sync_inbox.py --dry-run --lookback 14   # first run: see what it WOULD do
    python scripts/sync_inbox.py                            # daily: last 3 days
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from src.telemetry.logging import configure_logging  # noqa: E402
from src.workflows.inbox import run  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="classify and report; write nothing to Notion")
    ap.add_argument("--lookback", type=int, default=3, help="days of mail to consider (default 3)")
    args = ap.parse_args()
    configure_logging()
    print(run(dry_run=args.dry_run, lookback_days=args.lookback).as_text())
