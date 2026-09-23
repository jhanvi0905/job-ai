"""Deterministic years-of-experience extraction from a job description.

Zero tokens: regex only. A JD's overall requirement is usually the LARGEST
"N+ years of experience" figure (per-skill asks like "3+ years Python" are
smaller), so we take the max of the minimums. Only sentences that actually
talk about experience count — company-history lines ("founded 10 years ago")
must not.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_RANGE = re.compile(r"(\d{1,2})\s*(?:\+)?\s*(?:-|–|—|to)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)", re.I)
_PLUS = re.compile(r"(\d{1,2})\s*\+\s*(?:years?|yrs?)", re.I)
_PLAIN = re.compile(
    r"(?:at least|minimum(?: of)?|min\.?|over|more than)?\s*(\d{1,2})\s*(?:years?|yrs?)\b", re.I
)
_EXPERIENCE_WORDS = re.compile(r"experience|expertise|background|track record|hands-on", re.I)
_SOFT = re.compile(r"prefer|nice to have|bonus|ideally|a plus|desired|advantage", re.I)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;•\n])\s+|\s{2,}")


@dataclass
class YearsRequirement:
    min_years: int | None
    max_years: int | None
    evidence: str


def extract_required_years(description: str) -> YearsRequirement | None:
    """Returns the strongest (hard, non-'preferred') experience requirement,
    or None if the JD states none."""
    best_min: int | None = None
    best_max: int | None = None
    evidence = ""

    for sentence in _SENTENCE_SPLIT.split(description or ""):
        if not _EXPERIENCE_WORDS.search(sentence) or _SOFT.search(sentence):
            continue

        found: list[tuple[int, int | None]] = []
        for m in _RANGE.finditer(sentence):
            found.append((int(m.group(1)), int(m.group(2))))
        if not found:
            for m in _PLUS.finditer(sentence):
                found.append((int(m.group(1)), None))
        if not found:
            for m in _PLAIN.finditer(sentence):
                found.append((int(m.group(1)), None))

        for lo, hi in found:
            if lo > 25 or (hi is not None and hi > 30):  # "25 years in business" style noise
                continue
            if best_min is None or lo > best_min:
                best_min, best_max, evidence = lo, hi, sentence.strip()[:160]

    if best_min is None:
        return None
    return YearsRequirement(min_years=best_min, max_years=best_max, evidence=evidence)
