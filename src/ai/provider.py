"""LLM gateway (PRD §18): the ONE place any model call goes through.

Everything provider-specific and every cost/safety control lives here so no
pipeline stage can bypass it:

  * Retry with exponential backoff + full jitter, only for transient failures
    (timeouts, connection errors, 429, 5xx, unparseable output). Honours
    Retry-After. Never retries a 4xx that means "your request is wrong".
  * One schema-repair retry: if the output parses but fails the caller's
    validation, the model is shown the error once and asked to correct it.
  * Budgets, checked BEFORE every HTTP attempt: per-run dollars, per-day
    dollars (across runs, from the ledger) and a call-count backstop for
    providers that don't report cost. A blocked call makes no HTTP request.
  * Circuit breaker: after N consecutive failed calls the gateway stops
    calling for the rest of the run instead of burning retries on an outage.
  * Every HTTP attempt — successes and failures — is written to the ledger
    with tokens, cost, latency, the provider-resolved model version and a
    closed-vocabulary outcome, so failures are queryable, not just logged.

Concurrency: used from a thread pool. Budget checks read the ledger, so
concurrent workers can overshoot a cap by up to (workers x one call's cost) —
fractions of a cent; the caps are guardrails, not accounting.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import requests

from src.config import load_models
from src.jobs.schemas import AIUsageRecord
from src.ledger.codes import RETRYABLE_OUTCOMES
from src.ledger.db import Ledger
from src.telemetry.usage import record_usage

GATEWAY_DEFAULTS = {
    "timeout_s": 30,
    "max_attempts": 3,  # HTTP attempts per call for transient failures
    "backoff_base_s": 1.0,
    "backoff_max_s": 20.0,
    "circuit_breaker_failures": 5,
}
BUDGET_DEFAULTS = {"per_run_usd": 0.15, "per_day_usd": 0.30, "max_calls_per_run": 400}


class LLMError(Exception):
    def __init__(self, outcome: str, detail: str = ""):
        super().__init__(f"{outcome}: {detail}" if detail else outcome)
        self.outcome = outcome
        self.detail = detail


class BudgetExceeded(LLMError):
    pass


class CircuitOpen(LLMError):
    pass


class SchemaError(LLMError):
    pass


@dataclass
class _Attempt:
    outcome: str
    parsed: dict | None = None
    content: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost: float = 0.0
    resolved_model: str | None = None
    latency_ms: int = 0
    detail: str = ""
    retry_after: float | None = None


class LLMProvider:
    def __init__(
        self,
        ledger: Ledger | None = None,
        run_id: str | None = None,
        *,
        session: Any = None,
        sleep: Callable[[float], None] = time.sleep,
        rng: Callable[[], float] = random.random,
        config: dict | None = None,
        usage_sink: Callable[[AIUsageRecord], None] | None = record_usage,
    ):
        cfg = config if config is not None else load_models()
        provider_cfg = cfg["provider"]
        self.base_url = provider_cfg["base_url"].rstrip("/")
        self.api_key = os.environ.get(provider_cfg["api_key_env"], "")
        self.provider_name = provider_cfg["name"]
        self.gateway = {**GATEWAY_DEFAULTS, **cfg.get("gateway", {})}
        self.budget = {**BUDGET_DEFAULTS, **cfg.get("budget", {})}
        self.pricing = cfg.get("pricing", {})  # optional {model: {in_per_mtok, out_per_mtok}}
        self.ledger = ledger
        self.run_id = run_id
        self.session = session if session is not None else requests.Session()
        self._sleep = sleep
        self._rng = rng
        self._usage_sink = usage_sink
        self._lock = threading.Lock()
        self._consecutive_failures = 0

    # ------------------------------------------------------------------ public
    def _chat(
        self,
        *,
        model: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
        workflow: str,
        job_id: str | None,
        prompt_version: str | None = None,
        context: dict | None = None,
        validate: Callable[[dict], Any] | None = None,
    ) -> dict[str, Any]:
        """Returns the parsed JSON object. Raises LLMError (or a subclass)."""
        msgs = list(messages)
        input_hash = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()[:16]
        meta = dict(node=workflow, item_id=job_id, model=model, prompt_version=prompt_version,
                    input_hash=input_hash, context=context)

        http_attempts = 0  # counts toward max_attempts (transient retries)
        total = 0  # every HTTP attempt incl. the schema repair
        repaired = False

        while True:
            self._guard(total + 1, meta)
            total += 1
            result = self._attempt(model, msgs, max_tokens, temperature, validate)
            self._record(total, meta, result)

            if result.outcome == "ok":
                self._note_success()
                return result.parsed  # type: ignore[return-value]

            if result.outcome == "schema_invalid" and not repaired:
                repaired = True
                msgs = msgs + [
                    {"role": "assistant", "content": result.content or ""},
                    {"role": "user", "content": (
                        f"Your JSON failed validation: {result.detail[:300]}. "
                        "Return corrected JSON only, with exactly the requested schema."
                    )},
                ]
                continue

            if result.outcome in RETRYABLE_OUTCOMES:
                http_attempts += 1
                if http_attempts < self.gateway["max_attempts"]:
                    self._sleep(self._delay(http_attempts, result.retry_after))
                    continue

            self._note_failure()
            exc = SchemaError if result.outcome == "schema_invalid" else LLMError
            raise exc(result.outcome, result.detail)

    # --------------------------------------------------------------- one attempt
    def _attempt(self, model, messages, max_tokens, temperature, validate) -> _Attempt:
        start = time.monotonic()
        body = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }

        def done(**kw) -> _Attempt:
            return _Attempt(latency_ms=int((time.monotonic() - start) * 1000), **kw)

        try:
            resp = self.session.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=body,
                timeout=self.gateway["timeout_s"],
            )
        except requests.Timeout as exc:
            return done(outcome="timeout", detail=str(exc))
        except requests.RequestException as exc:
            return done(outcome="connection_error", detail=str(exc))

        status = resp.status_code
        if status == 429:
            return done(outcome="http_429", retry_after=_retry_after(resp), detail=(resp.text or "")[:200])
        if status >= 500:
            return done(outcome="http_5xx", detail=f"{status} {(resp.text or '')[:200]}")
        if status >= 400:
            return done(outcome="http_4xx", detail=f"{status} {(resp.text or '')[:200]}")

        try:
            payload = resp.json()
            choice = payload["choices"][0]
            content = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            return done(outcome="invalid_json", detail=f"unexpected response shape: {exc}")

        usage = payload.get("usage") or {}
        tokens_in, tokens_out = usage.get("prompt_tokens"), usage.get("completion_tokens")
        resolved = payload.get("model")
        cost = self._cost(payload, model, tokens_in, tokens_out)
        common = dict(content=content, tokens_in=tokens_in, tokens_out=tokens_out, cost=cost, resolved_model=resolved)

        if choice.get("finish_reason") == "length":
            return done(outcome="truncated", detail="output hit max_tokens", **common)
        try:
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError("top-level JSON is not an object")
        except ValueError as exc:
            return done(outcome="invalid_json", detail=str(exc), **common)

        if validate is not None:
            try:
                validate(parsed)
            except Exception as exc:  # noqa: BLE001 — any validation failure means "repair"
                return done(outcome="schema_invalid", detail=str(exc), parsed=parsed, **common)
        return done(outcome="ok", parsed=parsed, **common)

    # ----------------------------------------------------------------- guardrails
    def _guard(self, attempt_no: int, meta: dict) -> None:
        """Runs before EVERY HTTP attempt. Raising here means no request is made."""
        with self._lock:
            open_ = self._consecutive_failures >= self.gateway["circuit_breaker_failures"]
        if open_:
            self._record_blocked(attempt_no, meta, "circuit_open",
                                 f"{self.gateway['circuit_breaker_failures']} consecutive failed calls")
            raise CircuitOpen("circuit_open", "too many consecutive failures this run")

        if self.ledger is None or self.run_id is None:
            return
        reason = None
        if self.ledger.spent_in_run(self.run_id) >= self.budget["per_run_usd"]:
            reason = f"per_run ${self.budget['per_run_usd']}"
        elif self.ledger.spent_today() >= self.budget["per_day_usd"]:
            reason = f"per_day ${self.budget['per_day_usd']}"
        elif self.ledger.calls_in_run(self.run_id) >= self.budget["max_calls_per_run"]:
            reason = f"max_calls {self.budget['max_calls_per_run']}"
        if reason:
            self._record_blocked(attempt_no, meta, "budget_exceeded", reason)
            raise BudgetExceeded("budget_exceeded", reason)

    def _note_success(self) -> None:
        with self._lock:
            self._consecutive_failures = 0

    def _note_failure(self) -> None:
        with self._lock:
            self._consecutive_failures += 1

    # ------------------------------------------------------------------- helpers
    def _delay(self, n: int, retry_after: float | None) -> float:
        cap = self.gateway["backoff_max_s"]
        if retry_after is not None:  # the server said how long; believe it (capped)
            return min(retry_after, cap)
        return self._rng() * min(cap, self.gateway["backoff_base_s"] * (2 ** (n - 1)))  # full jitter

    def _cost(self, payload: dict, model: str, tokens_in, tokens_out) -> float:
        reported = ((payload.get("meta") or {}).get("usage") or {}).get("usd_spent")
        if reported is not None:
            return float(reported)
        price = self.pricing.get(model)
        if price and tokens_in is not None and tokens_out is not None:
            return (tokens_in * price["in_per_mtok"] + tokens_out * price["out_per_mtok"]) / 1_000_000
        return 0.0  # unknown; max_calls_per_run is the backstop for such providers

    def _record(self, attempt_no: int, meta: dict, r: _Attempt) -> None:
        if self.ledger is not None and self.run_id is not None:
            self.ledger.record_call(
                run_id=self.run_id, node=meta["node"], item_id=meta["item_id"], attempt=attempt_no,
                model_requested=meta["model"], model_resolved=r.resolved_model,
                prompt_version=meta["prompt_version"], outcome=r.outcome, tokens_in=r.tokens_in,
                tokens_out=r.tokens_out, cost_usd=r.cost, latency_ms=r.latency_ms,
                input_hash=meta["input_hash"], context=meta["context"], detail=r.detail,
            )
        if self._usage_sink is not None:
            self._usage_sink(
                AIUsageRecord(
                    timestamp=datetime.now(timezone.utc), workflow=meta["node"], job_id=meta["item_id"] or "",
                    model=meta["model"], provider=self.provider_name, input_tokens=r.tokens_in or 0,
                    output_tokens=r.tokens_out or 0, estimated_cost_usd=r.cost, latency_ms=r.latency_ms,
                    success=r.outcome == "ok", error=None if r.outcome == "ok" else r.outcome,
                )
            )

    def _record_blocked(self, attempt_no: int, meta: dict, outcome: str, detail: str) -> None:
        if self.ledger is not None and self.run_id is not None:
            self.ledger.record_call(
                run_id=self.run_id, node=meta["node"], item_id=meta["item_id"], attempt=attempt_no,
                model_requested=meta["model"], prompt_version=meta["prompt_version"], outcome=outcome,
                input_hash=meta["input_hash"], context=meta["context"], detail=detail,
            )


def _retry_after(resp) -> float | None:
    raw = (getattr(resp, "headers", None) or {}).get("Retry-After")
    try:
        return max(0.0, float(raw)) if raw is not None else None
    except (TypeError, ValueError):
        return None  # HTTP-date form: ignore, fall back to backoff
