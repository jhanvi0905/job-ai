"""Routing preferences: a deterministic, code-computed snapshot of revealed
preferences for a future LangGraph orchestrator to read as long-term memory.

Pure reshape of jobai.core.ledger.feedback.calibration() — recomputed fresh every
call, no incremental state, no LLM involvement.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from jobai.core.ledger.db import Ledger
from jobai.core.ledger.feedback import calibration


def build_routing_preferences(ledger: Ledger) -> dict:
    c = calibration(ledger)
    rejection_patterns = []
    for pri in sorted(c["by_priority"]):
        b = c["by_priority"][pri]
        decided = b["positive"] + b["rejected"]
        kept_rate = b["positive"] / decided if decided else None
        rejection_patterns.append({
            "priority": pri,
            "positive": b["positive"],
            "rejected": b["rejected"],
            "undecided": b["undecided"],
            "kept_rate": kept_rate,
        })
    return {
        "as_of": datetime.now(UTC).isoformat(),
        "rejection_patterns": rejection_patterns,
        "reject_reasons": c["reject_reasons"],
        # Reserved for explicit user-stated preferences set elsewhere (e.g. a
        # future settings UI); never computed here.
        "interaction_prefs": {},
    }


def save_routing_preferences(ledger: Ledger, path: str | Path = "data/routing_preferences.json") -> dict:
    prefs = build_routing_preferences(ledger)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prefs, indent=2))
    return prefs
