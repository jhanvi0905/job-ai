"""Human feedback: what YOU did with jobs the system surfaced.

Read from the Notion pages the run has already fetched for dedup, so it costs
no extra API call and no model tokens. Each observation is appended only when
Status or Reject Reason changed, so `human_outcomes` is a change history.

Report-only by design (Phase 3): this module measures agreement between the
system's verdicts and the human's; it never edits prompts, filters or rules.
"""
from __future__ import annotations

from src.ledger.codes import HUMAN_REJECT_REASONS
from src.ledger.db import Ledger


def sync_human_outcomes(ledger: Ledger, pages: list[dict], run_id: str | None = None) -> int:
    """Record status changes for automation-created pages. Returns rows appended."""
    n = 0
    for page in pages:
        fp = page.get("Job Fingerprint")
        if not fp or page.get("Source") != "Automation":
            continue
        if ledger.record_human_outcome(
            fingerprint=fp,
            status=page.get("Status"),
            reject_reason=page.get("Reject Reason"),
            notion_page_id=page.get("notion_page_id"),
            run_id=run_id,
        ):
            n += 1
    return n


# The Job Pipeline's Status options (checked against the live database). Grouped by
# what they say about the SYSTEM's suggestion: you engaged with it, dismissed it, or
# haven't decided. Withdrawn / No Response happen only after you applied, so they
# count as engaged. A status missing from all three sets is a bug (see the test).
POSITIVE = {"Shortlisted", "Applied", "Recruiter Screen", "Interview", "Assessment", "Final", "Offer", "Withdrawn", "No Response"}
NEGATIVE = {"Rejected"}
UNDECIDED = {"Discovered", "Watch"}


def calibration(ledger: Ledger) -> dict:
    """Agreement between the system's approvals and the human's latest status."""
    # A 'Rejected' set by an employer's email means you APPLIED — engagement with the
    # system's suggestion, not you dismissing it. Only human-set Rejected counts as a dismissal.
    employer_rejected = {
        r["fingerprint"] for r in ledger.query(
            "SELECT DISTINCT e.fingerprint FROM email_events e JOIN runs r ON r.run_id = e.run_id"
            " WHERE r.graph = 'inbox' AND e.reason_code = 'matched_updated' AND e.to_status = 'Rejected'"
        )
    }
    rows = ledger.query(
        "SELECT v.fingerprint, v.fit_band, v.priority, o.status, o.reject_reason FROM verdicts v"
        " JOIN (SELECT fingerprint, MAX(verdict_id) AS m FROM verdicts WHERE verdict='approved' GROUP BY fingerprint) l"
        "   ON l.m = v.verdict_id"
        " LEFT JOIN human_outcomes o ON o.outcome_id = (SELECT MAX(outcome_id) FROM human_outcomes WHERE fingerprint = v.fingerprint)"
    )
    by_priority: dict[str, dict[str, int]] = {}
    reasons: dict[str, int] = {}
    unknown_reasons: set[str] = set()
    for r in rows:
        if r["status"] == "Rejected" and r["fingerprint"] in employer_rejected:
            bucket = "positive"
        else:
            bucket = "positive" if r["status"] in POSITIVE else "rejected" if r["status"] in NEGATIVE else "undecided"
        by_priority.setdefault(r["priority"] or "?", {"positive": 0, "rejected": 0, "undecided": 0})[bucket] += 1
        if bucket == "rejected" and r["reject_reason"]:
            reasons[r["reject_reason"]] = reasons.get(r["reject_reason"], 0) + 1
            if r["reject_reason"] not in HUMAN_REJECT_REASONS:
                unknown_reasons.add(r["reject_reason"])
    return {"approved": len(rows), "by_priority": by_priority, "reject_reasons": reasons, "unknown_reasons": sorted(unknown_reasons)}


def format_calibration(c: dict) -> str:
    if not c["approved"]:
        return "No approved verdicts recorded yet."
    lines = [f"{c['approved']} jobs the system approved, by your latest decision:"]
    for pri in sorted(c["by_priority"]):
        b = c["by_priority"][pri]
        decided = b["positive"] + b["rejected"]
        rate = f"{b['positive'] / decided:.0%} kept" if decided else "no decisions yet"
        lines.append(f"  {pri}: {b['positive']} kept, {b['rejected']} rejected, {b['undecided']} undecided ({rate})")
    if c["reject_reasons"]:
        lines.append("  reject reasons: " + ", ".join(f"{k} x{v}" for k, v in sorted(c["reject_reasons"].items(), key=lambda kv: -kv[1])))
    if c["unknown_reasons"]:
        lines.append(f"  WARNING: Reject Reason values outside the known list: {c['unknown_reasons']}")
    return "\n".join(lines)
