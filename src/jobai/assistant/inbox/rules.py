"""Zero-token email triage: is this application mail, and can a rule classify it?

Order of work in the inbox run is deliberate: prefilter -> match to a pipeline
company -> rules -> (only if still ambiguous) the model. Mail that never reaches
a pipeline company costs nothing.
"""
from __future__ import annotations

import re

ATS_DOMAINS = (
    "greenhouse.io", "greenhouse-mail.io", "lever.co", "ashbyhq.com", "smartrecruiters.com", "myworkday.com",
    "workday.com", "icims.com", "jobvite.com", "taleo.net", "workablemail.com", "workable.com", "breezy.hr",
    "recruitee.com", "teamtailor.com", "bamboohr.com", "jazzhr.com", "applytojob.com", "hire.lever.co",
)

# Priority order matters: a rejection that says "thank you for applying" is a rejection.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("offer", re.compile(r"offer letter|pleased to offer|job offer|extend (you )?an offer|offer of employment", re.I)),
    ("rejection", re.compile(
        r"unfortunately|not (be )?(moving|proceeding) forward|decided to (move|proceed|go) (forward )?with (other|another)"
        r"|no longer (being )?considered|regret to (inform|tell)|not (been )?selected|position (has been|is now) filled"
        r"|will not be (moving|proceeding)|other candidates", re.I)),
    ("assessment", re.compile(r"coding (challenge|assessment|test)|take[- ]home|hackerrank|codility|codesignal|online assessment|technical assessment", re.I)),
    ("interview_request", re.compile(
        r"schedule (a|an|your|the)? ?(call|interview|chat|conversation|time)|invite you to (an? )?(interview|call|chat)"
        r"|(like|love) to (invite|schedule|speak|chat|meet|connect)|book a (time|slot)|calendly\.com|your availability|interview (invitation|with)", re.I)),
    ("confirmation", re.compile(
        r"thank(s| you) for (applying|your application|your interest)|(application|resume) (has been |was )?(successfully )?(received|submitted)"
        r"|we('ve| have) received your (application|resume)|application (confirmation|received)|successfully applied", re.I)),
]


def sender_is_ats(domain: str) -> bool:
    d = domain.lower()
    return any(d == a or d.endswith("." + a) for a in ATS_DOMAINS)


def matched_classes(text: str) -> list[str]:
    return [name for name, pat in _PATTERNS if pat.search(text)]


def looks_like_application_mail(domain: str, subject: str, snippet: str) -> bool:
    return sender_is_ats(domain) or bool(matched_classes(f"{subject} {snippet}"))


def classify_by_rules(subject: str, snippet: str) -> tuple[str | None, float]:
    """(class, confidence). A single unambiguous pattern family -> confident.
    Rejection wins over confirmation (the common 'thanks for applying... unfortunately').
    Two other families at once, or none -> (None, 0): the model decides."""
    hits = matched_classes(f"{subject} {snippet}")
    if not hits:
        return None, 0.0
    if len(hits) == 1:
        return hits[0], 0.9
    if hits[0] == "offer" or (hits[0] == "rejection" and set(hits[1:]) <= {"confirmation"}):
        return hits[0], 0.85
    return None, 0.0
