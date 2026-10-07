"""Fixed-window rate limiting in Postgres (no Redis).

One row per (key, window_start); a hit is a single atomic
`INSERT ... ON CONFLICT DO UPDATE SET count = count + 1 RETURNING count`
in its own short transaction (never the request's: a long request must not hold
the counter row lock, and a request that later fails still counts).

Fixed windows allow up to 2x the limit across a window boundary; fine for
abuse/cost protection, which is all this is for. Fails OPEN on a database
error (logged): the per-user quotas and $ guards still fail closed.

Limits (RULES) — tune here:
  waitlist      5 / hour   per client IP   (POST /waitlist)
  write        60 / minute per user        (every authenticated POST/PUT/PATCH/DELETE)
  feed_refresh  6 / hour   per user        (POST /feed/refresh)
  tailor       20 / hour   per user        (POST /jobs/{id}/tailor)
"""
from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from jobai.product.db.models import RateLimitCounter, User

log = logging.getLogger(__name__)

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True)
class Rule:
    limit: int
    window_s: int


RULES: dict[str, Rule] = {
    "waitlist": Rule(5, 3600),
    "write": Rule(60, 60),
    "feed_refresh": Rule(6, 3600),
    "tailor": Rule(20, 3600),
}


def enabled(request: Request) -> bool:
    flag = getattr(request.app.state, "rate_limits_enabled", None)
    if flag is not None:
        return bool(flag)
    return os.environ.get("RATE_LIMITS_ENABLED", "true").lower() not in ("0", "false", "no")


def client_ip(request: Request) -> str:
    """Fly's edge sets Fly-Client-IP (and strips client-sent copies). Off Fly,
    fall back to the socket peer — never to X-Forwarded-For, which is spoofable."""
    ip = (request.headers.get("fly-client-ip") or "").strip()
    if ip:
        return ip[:64]
    return request.client.host if request.client else "unknown"


def _window_start(now: datetime, window_s: int) -> datetime:
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - epoch % window_s, UTC)


def hit(session_factory: sessionmaker[Session], key: str, rule: Rule, now: datetime | None = None) -> tuple[int, int]:
    """Count one hit. Returns (count_in_window, seconds_until_window_resets)."""
    now = now or datetime.now(UTC)
    start = _window_start(now, rule.window_s)
    reset_in = max(1, math.ceil((start + timedelta(seconds=rule.window_s) - now).total_seconds()))
    with session_factory() as s:
        ins = pg_insert if s.bind.dialect.name == "postgresql" else sqlite_insert
        stmt = ins(RateLimitCounter).values(key=key[:160], window_start=start, count=1)
        stmt = stmt.on_conflict_do_update(index_elements=["key", "window_start"],
                                          set_={"count": RateLimitCounter.count + 1}).returning(RateLimitCounter.count)
        count = int(s.execute(stmt).scalar_one())
        s.commit()
    return count, reset_in


def check(request: Request, scope: str, subject: str | int) -> None:
    """Raise 429 (code `rate_limited`, Retry-After) when over the limit."""
    if not enabled(request):
        return
    rule = RULES[scope]
    try:
        count, reset_in = hit(request.app.state.session_factory, f"{scope}:{subject}", rule)
    except SQLAlchemyError:
        log.exception("rate limiter unavailable; allowing request", extra={"scope": scope})
        return
    if count > rule.limit:
        log.info("rate limited", extra={"scope": scope, "limit": rule.limit})
        raise HTTPException(429, f"too many requests; retry in {reset_in}s",
                            headers={"Retry-After": str(reset_in)})


# ------------------------------------------------------------- dependencies
def limit_by_ip(scope: str):
    def dep(request: Request) -> None:
        check(request, scope, client_ip(request))
    return dep


def limit_by_user(scope: str):
    from jobai.product.services.auth import get_current_user  # lazy: auth imports this module

    def dep(request: Request, user: User = Depends(get_current_user)) -> None:
        check(request, scope, user.id)
    return dep
