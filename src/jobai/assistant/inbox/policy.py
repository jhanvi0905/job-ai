"""Status transition policy. Pure function; every rule here is a promise to the user:

  * Never move a job backwards.
  * Never override a status the user owns as final (Rejected, Withdrawn), and
    never turn an Offer into a Rejected automatically — flag it instead.
  * A confirmation never overrides anything beyond 'Applied'.
"""
from __future__ import annotations

import re

RANK = {
    "Discovered": 0, "Watch": 0, "Shortlisted": 1, "Applied": 2, "No Response": 2,
    "Recruiter Screen": 3, "Assessment": 3, "Interview": 4, "Final": 5, "Offer": 6,
}
PROTECTED = {"Rejected", "Withdrawn"}
_RECRUITER = re.compile(r"recruiter|intro(ductory)? (call|chat)|initial (call|chat|conversation)|quick (call|chat)|phone screen|screening", re.I)


def target_status(klass: str, text: str) -> str | None:
    if klass == "confirmation":
        return "Applied"
    if klass == "assessment":
        return "Assessment"
    if klass == "interview_request":
        return "Recruiter Screen" if _RECRUITER.search(text) else "Interview"
    if klass == "offer":
        return "Offer"
    if klass == "rejection":
        return "Rejected"
    return None


def decide(current: str | None, klass: str, text: str = "") -> tuple[str, str | None]:
    """-> (outcome, new_status) with outcome in update | no_change | blocked_protected | other_class."""
    target = target_status(klass, text)
    if target is None:
        return "other_class", None
    current = current or "Discovered"
    if current == target:
        return "no_change", None
    if current in PROTECTED:
        return "blocked_protected", None
    if target == "Rejected":
        return ("blocked_protected", None) if current == "Offer" else ("update", "Rejected")
    if RANK.get(current, 0) >= RANK[target]:
        return "no_change", None
    return "update", target
