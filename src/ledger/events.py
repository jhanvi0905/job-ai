"""Pipeline-facing wrapper around the ledger's item events.

Two modes, on purpose:
  * strict (tests): any bad code or duplicate terminal event RAISES, so an
    invariant violation fails the test that caused it.
  * lenient (production): observability must never take down a run, so errors
    are logged and counted (`write_failures`); the run marks itself degraded
    instead of silently losing data.
"""
from __future__ import annotations

import logging
import sqlite3

from src.ledger.db import Ledger

logger = logging.getLogger(__name__)


class Events:
    def __init__(self, ledger: Ledger, run_id: str, strict: bool = False):
        self.ledger = ledger
        self.run_id = run_id
        self.strict = strict
        self.write_failures = 0

    def item(self, node: str, item_id: str, disposition: str, code: str, detail: str | None = None) -> None:
        self._safely(
            lambda: self.ledger.record_event(
                run_id=self.run_id, item_id=item_id, node=node, disposition=disposition, reason_code=code, detail=detail
            ),
            f"event {node}/{code} for {item_id}",
        )

    def funnel(self, node: str, counts: dict[str, int]) -> None:
        self._safely(lambda: self.ledger.record_funnel(self.run_id, node, dict(counts)), f"funnel {node}")

    def _safely(self, fn, what: str) -> None:
        try:
            fn()
        except (sqlite3.Error, ValueError) as exc:
            if self.strict:
                raise
            self.write_failures += 1
            logger.error("ledger write failed (%s): %s", what, exc)


class _NullEvents:
    """No-op sink for callers that don't record (dry tools, older tests)."""

    write_failures = 0

    def item(self, *a, **k) -> None:
        pass

    def funnel(self, *a, **k) -> None:
        pass


NULL_EVENTS = _NullEvents()
