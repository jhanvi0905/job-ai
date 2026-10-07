"""Telemetry record types (no engine dependencies)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AIUsageRecord(BaseModel):
    """One row per model call — never rely on provider dashboards alone."""

    timestamp: datetime
    workflow: str
    job_id: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    latency_ms: int
    cache_hit: bool = False
    success: bool = True
    error: str | None = None
