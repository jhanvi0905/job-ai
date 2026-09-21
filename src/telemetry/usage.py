"""AI usage telemetry (PRD §20). Appends one JSON line per model call to a
local file — deliberately not dependent on provider dashboards."""
from __future__ import annotations

import json
from pathlib import Path

from src.jobs.schemas import AIUsageRecord

USAGE_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "ai_usage.jsonl"


def record_usage(record: AIUsageRecord) -> None:
    USAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with USAGE_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")
