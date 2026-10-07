"""Per-user LLM access: the existing gateway (retries, repair, circuit breaker,
fail-closed budget guard) with a tenant-scoped ledger underneath.

LLMProvider already accepts any object with Ledger's four methods, so instead
of forking it we hand it `UserLedger`: calls land in `llm_calls` with user_id,
and the per-run / per-user-per-day / call-count guards read from that table.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from jobai.core.config import load_models
from jobai.engine.ai.provider import LLMProvider
from jobai.product.db.models import LLMCall

# Guardrail defaults for one tenant; override per deployment in models.yaml `budget`.
USER_BUDGET_DEFAULTS = {"per_run_usd": 0.10, "per_user_day_usd": 0.25, "max_calls_per_run": 200}
_BLOCKED = ("budget_exceeded", "circuit_open")  # guardrail rows: no HTTP call was made


class UserLedger:
    """Duck-typed stand-in for jobai.core.ledger.db.Ledger scoped to one user. Each
    operation uses its own short session, so it is safe from worker threads."""

    def __init__(self, session_factory: sessionmaker[Session], user_id: int):
        self._factory = session_factory
        self.user_id = user_id

    def record_call(
        self, *, run_id: str, node: str, attempt: int, model_requested: str, outcome: str,
        item_id: str | None = None, model_resolved: str | None = None, tokens_in: int | None = None,
        tokens_out: int | None = None, cost_usd: float = 0.0, **_unused: Any,
    ) -> None:
        with self._factory() as s:
            s.add(LLMCall(
                user_id=self.user_id, run_id=run_id, node=node[:32], item_id=item_id[:64] if item_id else None,
                model=(model_resolved or model_requested)[:64], tokens_in=tokens_in, tokens_out=tokens_out,
                cost_usd=cost_usd, outcome=outcome[:24],
            ))
            s.commit()

    def _sum(self, *where) -> float:
        with self._factory() as s:
            return float(s.scalar(select(func.coalesce(func.sum(LLMCall.cost_usd), 0.0)).where(LLMCall.user_id == self.user_id, *where)))

    def spent_in_run(self, run_id: str) -> float:
        return self._sum(LLMCall.run_id == run_id)

    def spent_today(self) -> float:
        """This user's spend since 00:00 UTC — the per-user daily guard."""
        start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        return self._sum(LLMCall.created_at >= start)

    def calls_in_run(self, run_id: str) -> int:
        with self._factory() as s:
            return int(s.scalar(select(func.count()).select_from(LLMCall).where(
                LLMCall.user_id == self.user_id, LLMCall.run_id == run_id, LLMCall.outcome.not_in(_BLOCKED))))


def make_user_provider(
    session_factory: sessionmaker[Session],
    user_id: int,
    run_id: str | None = None,
    *,
    http_session: Any = None,
    config: dict | None = None,
    sleep: Callable[[float], None] | None = None,
) -> LLMProvider:
    """A gateway whose spend is attributed to `user_id`. A run_id is always
    set (generated if absent): the gateway skips budget checks without one, and
    that must never happen silently. `http_session`/`config`/`sleep` are test seams."""
    cfg = dict(config if config is not None else load_models())
    budget = {**USER_BUDGET_DEFAULTS, **cfg.get("budget", {})}
    # The gateway's own per_day_usd reads spent_today(), which UserLedger scopes to this user.
    budget["per_day_usd"] = budget.get("per_user_day_usd", USER_BUDGET_DEFAULTS["per_user_day_usd"])
    cfg["budget"] = budget
    kwargs: dict[str, Any] = {}
    if sleep is not None:
        kwargs["sleep"] = sleep
    return LLMProvider(
        UserLedger(session_factory, user_id), run_id or f"u{user_id}-{uuid.uuid4().hex[:12]}",
        session=http_session, config=cfg, usage_sink=None, **kwargs,
    )
