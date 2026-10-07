"""Per-user daily caps — the SaaS form of `budget.per_day_usd`. Checked BEFORE
any LLM spend; fail closed (raise, never silently proceed)."""
from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from jobai.product.db.models import UsageCounter, User

# kind -> {plan: per-day cap}. Single place to tune pricing tiers.
PLAN_LIMITS: dict[str, dict[str, int]] = {
    "free": {"triage": 40, "deep_match": 5, "tailor": 1, "resume_parse": 2},
    "pro": {"triage": 400, "deep_match": 60, "tailor": 15, "resume_parse": 10},
}
KINDS = tuple(PLAN_LIMITS["free"])


class QuotaExceeded(Exception):
    def __init__(self, kind: str, limit: int):
        super().__init__(f"daily {kind} limit reached ({limit})")
        self.kind, self.limit = kind, limit


def _today() -> date:
    return datetime.now(UTC).date()


def used_today(session: Session, user_id: int, kind: str) -> int:
    row = session.get(UsageCounter, (user_id, _today(), kind))
    return row.count if row else 0


def remaining(session: Session, user_id: int, kind: str) -> int:
    user = session.get(User, user_id)
    return max(0, PLAN_LIMITS[user.plan][kind] - used_today(session, user_id, kind))


def consume(session: Session, user_id: int, kind: str, n: int = 1) -> None:
    """Reserve `n` units or raise QuotaExceeded (nothing consumed on raise)."""
    if kind not in KINDS:
        raise ValueError(f"unknown quota kind: {kind}")
    user = session.get(User, user_id)
    limit = PLAN_LIMITS[user.plan][kind]
    row = session.get(UsageCounter, (user_id, _today(), kind))
    current = row.count if row else 0
    if current + n > limit:
        raise QuotaExceeded(kind, limit)
    if row is None:
        session.add(UsageCounter(user_id=user_id, day=_today(), kind=kind, count=n))
    else:
        row.count = current + n
    session.flush()
