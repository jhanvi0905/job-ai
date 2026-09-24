#!/usr/bin/env python3
"""Print the ledger tripwires. Read-only: never calls a model, never touches Notion.

    python scripts/health.py            # exit 1 if any tripwire is CRITICAL
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_models  # noqa: E402
from src.ledger.db import Ledger  # noqa: E402
from src.ledger.health import check  # noqa: E402

MARK = {"ok": "  ok  ", "warn": " WARN ", "crit": " CRIT "}

if __name__ == "__main__":
    ledger = Ledger()
    findings = check(ledger, load_models().get("budget", {}))
    ledger.close()
    for f in findings:
        print(f"[{MARK[f.level]}] {f.name:<15} {f.message}")
    sys.exit(1 if any(f.level == "crit" for f in findings) else 0)
