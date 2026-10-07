"""Match an email to ONE pipeline page — or refuse. Wrong matches are worse than
missed ones (they would move the wrong job's status), so ambiguity is a
first-class, counted outcome, never a guess."""
from __future__ import annotations

import re
from dataclasses import dataclass

from jobai.core.ledger.feedback import POSITIVE

_SUFFIXES = {"inc", "llc", "ltd", "limited", "corp", "corporation", "co", "gmbh", "plc", "pvt", "technologies", "technology", "labs", "the"}
_STOP = {"the", "and", "for", "of", "a", "an", "to", "in", "at", "with", "senior", "sr", "junior", "jr", "remote", "global", "india", "ii", "iii"}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())).strip()


def company_key(name: str) -> str:
    words = [w for w in _norm(name).split() if w not in _SUFFIXES]
    return " ".join(words)


def _contains_phrase(haystack: str, phrase: str) -> bool:
    return bool(phrase) and re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", haystack) is not None


def _domain_label(domain: str) -> str:
    parts = domain.lower().split(".")
    return parts[-2] if len(parts) >= 2 else ""


def mentions_company(company: str, sender_name: str, sender_domain: str, subject: str, snippet: str) -> bool:
    key = company_key(company)
    if len(key.replace(" ", "")) < 3:
        return False
    text = _norm(f"{sender_name} {subject} {snippet}")
    return _contains_phrase(text, key) or _domain_label(sender_domain) == key.replace(" ", "")


def _role_tokens(role: str) -> set[str]:
    return {t for t in _norm(role).split() if t not in _STOP and len(t) > 1}


def role_score(role: str, subject: str, snippet: str) -> float:
    tokens = _role_tokens(role)
    if not tokens:
        return 0.0
    text = set(_norm(f"{subject} {snippet}").split())
    return len(tokens & text) / len(tokens)


@dataclass(frozen=True)
class Match:
    page: dict | None
    method: str          # company | company+role | company+status | none | ambiguous
    candidates: int = 0


def match_email(pages: list[dict], sender_name: str, sender_domain: str, subject: str, snippet: str) -> Match:
    cands = [
        p for p in pages
        if p.get("Job Fingerprint") and p.get("Company")
        and mentions_company(p["Company"], sender_name, sender_domain, subject, snippet)
    ]
    if not cands:
        return Match(None, "none", 0)
    if len(cands) == 1:
        return Match(cands[0], "company", 1)
    scored = sorted(((role_score(p.get("Role") or "", subject, snippet), p) for p in cands), key=lambda t: -t[0])
    top, second = scored[0][0], scored[1][0]
    if top >= 0.6 and top > second:
        return Match(scored[0][1], "company+role", len(cands))
    engaged = [p for p in cands if p.get("Status") in POSITIVE]
    if len(engaged) == 1:
        return Match(engaged[0], "company+status", len(cands))
    return Match(None, "ambiguous", len(cands))


_TITLE_WORDS = re.compile(
    r"\b(engineer|scientist|developer|architect|analyst|manager|researcher|designer|specialist|consultant|lead|director)\b", re.I
)


def role_conflict(role: str, company: str, subject: str, snippet: str) -> bool:
    """True when the email clearly talks about A role (it contains a job-title word
    outside the company name) but not THIS page's role. A company-only match can
    otherwise attach 'we won't be moving forward with your AI Engineer application'
    to a different role's page. Emails that name no role are not in conflict.
    Conservative on purpose: a false conflict only skips an auto-update."""
    text = f"{subject} {snippet}"
    for word in company_key(company).split():
        text = re.sub(rf"\b{re.escape(word)}\b", " ", text, flags=re.I)
    return bool(_TITLE_WORDS.search(text)) and role_score(role, text, "") < 0.5
