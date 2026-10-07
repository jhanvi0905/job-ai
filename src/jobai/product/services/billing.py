"""Credit ledger + payment-provider port.

Credits are an append-only ledger (balance = SUM(delta)). Every grant/spend can
carry a `ref` (payment event id, tailor input hash) and is idempotent on
(user_id, ref): a retried webhook or a retried request never double-charges or
double-grants.

Payment port: Stripe (or any PSP) is OUT OF SCOPE here. An adapter implements
`PaymentProvider.parse_event(headers, body)`, verifying the PSP's own signature
scheme and returning a `PaymentEvent` (or raising `WebhookError`). The shipped
`HmacPaymentProvider` is the stub: shared secret in PAYMENT_WEBHOOK_SECRET,
hex HMAC-SHA256 of the raw body in the `X-Signature` header, JSON body
{"event_id", "user_id", "credits"}. The router only ever calls `grant`.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jobai.product.db.models import CreditLedger


class InsufficientCredits(Exception):
    pass


class WebhookError(Exception):
    pass


def balance(session: Session, user_id: int) -> int:
    return int(session.scalar(select(func.coalesce(func.sum(CreditLedger.delta), 0)).where(CreditLedger.user_id == user_id)) or 0)


def _seen(session: Session, user_id: int, ref: str | None) -> bool:
    if ref is None:
        return False
    return session.scalar(select(CreditLedger.id).where(CreditLedger.user_id == user_id, CreditLedger.ref == ref)) is not None


def grant(session: Session, user_id: int, n: int, reason: str = "purchase", ref: str | None = None) -> bool:
    """Add `n` credits. Returns False (no-op) if `ref` was already applied."""
    if n <= 0:
        raise ValueError("grant amount must be positive")
    if _seen(session, user_id, ref):
        return False
    session.add(CreditLedger(user_id=user_id, delta=n, reason=reason, ref=ref))
    session.flush()
    return True


def spend(session: Session, user_id: int, n: int = 1, reason: str = "tailor", ref: str | None = None) -> bool:
    """Debit `n` credits or raise InsufficientCredits. False (no-op) if `ref` already applied."""
    if n <= 0:
        raise ValueError("spend amount must be positive")
    if _seen(session, user_id, ref):
        return False
    if balance(session, user_id) < n:
        raise InsufficientCredits(f"need {n} credit(s)")
    session.add(CreditLedger(user_id=user_id, delta=-n, reason=reason, ref=ref))
    session.flush()
    return True


@dataclass(frozen=True)
class PaymentEvent:
    event_id: str
    user_id: int
    credits: int


class PaymentProvider(Protocol):
    def parse_event(self, headers: Mapping[str, str], body: bytes) -> PaymentEvent:
        """Verify authenticity and translate the PSP payload; raise WebhookError otherwise."""


class HmacPaymentProvider:
    def __init__(self, secret: str | None = None):
        self.secret = secret if secret is not None else os.environ.get("PAYMENT_WEBHOOK_SECRET", "")

    def parse_event(self, headers: Mapping[str, str], body: bytes) -> PaymentEvent:
        if not self.secret:
            raise WebhookError("webhook secret not configured")
        given = {k.lower(): v for k, v in headers.items()}.get("x-signature", "")
        expected = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(given, expected):
            raise WebhookError("bad signature")
        try:
            data = json.loads(body)
            event = PaymentEvent(str(data["event_id"]), int(data["user_id"]), int(data["credits"]))
        except (ValueError, KeyError, TypeError) as exc:
            raise WebhookError("malformed payload") from exc
        if event.credits <= 0:
            raise WebhookError("credits must be positive")
        return event
