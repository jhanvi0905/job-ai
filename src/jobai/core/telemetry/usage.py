"""AI usage telemetry (PRD §20). Appends one JSON line per model call to a
local file — deliberately not dependent on provider dashboards."""
from __future__ import annotations

import json
from datetime import datetime

from jobai.core.paths import DATA_DIR
from jobai.core.telemetry.records import AIUsageRecord

USAGE_LOG_PATH = DATA_DIR / "ai_usage.jsonl"


def record_usage(record: AIUsageRecord) -> None:
    USAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with USAGE_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")


def estimate_run_cost(workflow: str, since: datetime) -> float:
    """Sums real recorded cost (AIUsageRecord.estimated_cost_usd — itself the
    provider's own returned cost, see LLMProvider._chat) for a given workflow
    since a timestamp. Used to report what a single run actually spent,
    without needing calls to thread cost back up through return values."""
    if not USAGE_LOG_PATH.exists():
        return 0.0
    total = 0.0
    with USAGE_LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("workflow") != workflow:
                continue
            if datetime.fromisoformat(record["timestamp"]) < since:
                continue
            total += record.get("estimated_cost_usd", 0.0)
    return total
