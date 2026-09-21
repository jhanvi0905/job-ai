"""Provider abstraction (PRD §18). Everything provider-specific sits behind
this — swapping AI/ML API for another OpenAI-compatible endpoint should never
require touching classifier.py / matcher.py / the workflow.

Not wired into the Phase 1 pipeline yet — Phase 2 work. Kept here now so the
repo structure matches the target architecture from day one.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

import requests

from src.config import load_models
from src.jobs.schemas import AIUsageRecord
from src.telemetry.usage import record_usage


class LLMProvider:
    """Thin OpenAI-compatible chat-completions client, config-driven model
    routing, mandatory usage telemetry on every call."""

    def __init__(self):
        cfg = load_models()["provider"]
        self.base_url = cfg["base_url"].rstrip("/")
        self.api_key = os.environ.get(cfg["api_key_env"], "")
        self.provider_name = cfg["name"]

    def _chat(
        self,
        *,
        model: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
        workflow: str,
        job_id: str,
    ) -> dict[str, Any]:
        start = time.monotonic()
        success = True
        error = None
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        content = "{}"
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "response_format": {"type": "json_object"},
                },
                timeout=30,
            )
            resp.raise_for_status()
            payload = resp.json()
            usage = payload.get("usage", usage)
            content = payload["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001 — always record telemetry, even on failure
            success = False
            error = str(exc)
            raise
        finally:
            record_usage(
                AIUsageRecord(
                    timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                    workflow=workflow,
                    job_id=job_id,
                    model=model,
                    provider=self.provider_name,
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                    estimated_cost_usd=0.0,  # filled in once real per-model pricing is confirmed
                    latency_ms=int((time.monotonic() - start) * 1000),
                    success=success,
                    error=error,
                )
            )
        return json.loads(content)
