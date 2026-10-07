"""Conservation of items: nothing may vanish between pipeline stages.

Every item entering a node must leave it with exactly ONE terminal event, and
the flow between nodes must balance:

    fetch.normalized  ==  sum(stage0 funnel)                 (stage 0 accounts for everyone)
    stage0.passed     ==  #dedupe events
    dedupe passed     ==  triage events   (same items)
    triage passed     ==  match events    (same items)
    match passed      ==  write events    (same items; skipped for dry runs)

A violation means an item silently disappeared (an exception swallowed, a list
truncated, a branch that forgot to record) — exactly the failure that produces
no error and no log line. Returns human-readable violations; [] means balanced.
"""
from __future__ import annotations

from jobai.core.ledger.db import Ledger

_CHAIN = [("dedupe", "triage"), ("triage", "match"), ("match", "write")]


def _ids(ledger: Ledger, run_id: str, node: str, passed_only: bool = False) -> set[str]:
    sql = "SELECT item_id FROM events WHERE run_id = ? AND node = ?" + (" AND disposition = 'passed'" if passed_only else "")
    return {r["item_id"] for r in ledger.query(sql, (run_id, node))}


def _funnel(ledger: Ledger, run_id: str, node: str) -> dict[str, int]:
    return {r["reason_code"]: r["n"] for r in ledger.query("SELECT reason_code, n FROM funnel WHERE run_id = ? AND node = ?", (run_id, node))}


def _sample(ids: set[str], k: int = 3) -> str:
    shown = ", ".join(sorted(ids)[:k])
    return shown + (f" (+{len(ids) - k} more)" if len(ids) > k else "")


def check_conservation(ledger: Ledger, run_id: str, *, dry_run: bool = False) -> list[str]:
    violations: list[str] = []

    fetched = _funnel(ledger, run_id, "fetch").get("normalized", 0)
    stage0 = _funnel(ledger, run_id, "stage0")
    accounted = sum(stage0.values())
    if accounted != fetched:
        violations.append(f"stage0 accounted for {accounted} items but fetch normalized {fetched} ({fetched - accounted:+d} unaccounted)")

    passed0 = stage0.get("passed_stage0", 0)
    dedupe_ids = _ids(ledger, run_id, "dedupe")
    if len(dedupe_ids) != passed0:
        violations.append(f"stage0 passed {passed0} items but dedupe recorded {len(dedupe_ids)}")

    for upstream, downstream in _CHAIN:
        if downstream == "write" and dry_run:
            continue
        expected = _ids(ledger, run_id, upstream, passed_only=True)
        actual = _ids(ledger, run_id, downstream)
        missing, unexpected = expected - actual, actual - expected
        if missing:
            violations.append(f"{len(missing)} item(s) passed {upstream} but have no {downstream} event: {_sample(missing)}")
        if unexpected:
            violations.append(f"{len(unexpected)} item(s) reached {downstream} without passing {upstream}: {_sample(unexpected)}")
    return violations
