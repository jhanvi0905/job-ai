"""Inbox run: read application emails, advance Notion statuses. READ-ONLY on Gmail.

  list ids -> drop already-settled -> fetch metadata -> for each message, oldest first:
    prefilter (0 tokens) -> match to ONE pipeline page (0 tokens) -> rules (0 tokens)
    -> model only if rules can't settle -> status policy -> Notion update

Every message gets exactly one terminal row in email_events (or is retried next
run: llm_error / notion_error). The run checks its own books at the end.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from src.ai.email_classifier import classify_email
from src.ai.provider import LLMProvider
from src.inbox import policy, rules
from src.inbox.gmail import GmailReader, Message
from src.inbox.matcher import match_email
from src.ledger.db import Ledger

logger = logging.getLogger(__name__)
MIN_CONFIDENCE = 0.7


@dataclass
class InboxSummary:
    fetched: int = 0
    already_settled: int = 0
    processed: int = 0
    by_reason: dict[str, int] = field(default_factory=dict)
    updates: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def count(self, reason: str) -> None:
        self.by_reason[reason] = self.by_reason.get(reason, 0) + 1

    def as_text(self) -> str:
        lines = [f"{self.fetched} emails in window, {self.already_settled} already handled, {self.processed} looked at"]
        lines += [f"  {k}: {v}" for k, v in sorted(self.by_reason.items(), key=lambda kv: -kv[1])]
        if self.updates:
            lines.append("STATUS UPDATES:")
            lines += [f"  {u}" for u in self.updates]
        if self.errors:
            lines.append("ERRORS:")
            lines += [f"  {e}" for e in self.errors]
        return "\n".join(lines)


def _process(msg: Message, pages: list[dict], provider: LLMProvider, notion, dry_run: bool, ledger: Ledger,
             run_id: str, summary: InboxSummary) -> None:
    base = dict(run_id=run_id, message_id=msg.id, thread_id=msg.thread_id, received_at=msg.received_at.isoformat(),
                sender_domain=msg.sender_domain, subject=msg.subject, snippet=msg.snippet)

    def done(reason: str, **extra) -> None:
        ledger.record_email_event(reason_code=reason, **base, **extra)
        summary.count(reason)

    if not rules.looks_like_application_mail(msg.sender_domain, msg.subject, msg.snippet):
        return done("not_application_mail")

    m = match_email(pages, msg.sender_name, msg.sender_domain, msg.subject, msg.snippet)
    if m.page is None:
        return done("ambiguous_match" if m.method == "ambiguous" else "no_company_match",
                    match_method=m.method, detail=f"{m.candidates} candidate page(s)")
    page = m.page
    fp, company, role, current = page["Job Fingerprint"], page.get("Company"), page.get("Role"), page.get("Status")
    ident = dict(fingerprint=fp, match_method=m.method, from_status=current)

    klass, conf = rules.classify_by_rules(msg.subject, msg.snippet)
    method = "rules"
    if klass is None:
        method = "llm"
        try:
            klass, conf = classify_email(company=company or "", role=role or "", domain=msg.sender_domain,
                                         subject=msg.subject, snippet=msg.snippet, provider=provider, message_id=msg.id)
        except Exception as exc:  # noqa: BLE001 — retried next run
            summary.errors.append(f"classify {msg.id}: {type(exc).__name__}: {exc}"[:200])
            return done("llm_error", method=method, detail=str(exc), **ident)
    cls = dict(classification=klass, confidence=conf, method=method)

    if conf < MIN_CONFIDENCE:
        return done("low_confidence", **cls, **ident)
    outcome, new_status = policy.decide(current, klass, f"{msg.subject} {msg.snippet}")
    if outcome != "update":
        return done(outcome, **cls, **ident)

    if not dry_run:
        props = {"Status": new_status, "Last Update": date.today().isoformat()}
        if new_status == "Applied" and not page.get("Applied Date"):
            props["Applied Date"] = msg.received_at.date().isoformat()
        if not page.get("Notes"):  # never overwrite your own notes
            props["Notes"] = f"Auto: {klass.replace('_', ' ')} email from {msg.sender_domain} on {msg.received_at.date().isoformat()}"
        try:
            notion.update_job_page(page["notion_page_id"], props)
        except Exception as exc:  # noqa: BLE001
            summary.errors.append(f"notion {fp}: {type(exc).__name__}: {exc}"[:200])
            return done("notion_error", **cls, **ident, to_status=new_status, detail=str(exc))
    page["Status"] = new_status  # later emails in this run see the new state
    summary.updates.append(f"{company} — {role}: {current} -> {new_status} ({klass}, {msg.sender_domain})")
    done("matched_updated", **cls, **ident, to_status=new_status)


def run(*, dry_run: bool = False, lookback_days: int = 3, reader: GmailReader | None = None, notion=None,
        provider_factory=LLMProvider) -> InboxSummary:
    from src.config import load_models
    from src.integrations.notion import NotionClient

    summary = InboxSummary()
    ledger = Ledger()
    run_id = ledger.start_run("inbox-dry" if dry_run else "inbox", budget_usd=load_models().get("budget", {}).get("per_run_usd"))
    status, note = "ok", None
    try:
        reader = reader or GmailReader()
        notion = notion or NotionClient()
        provider = provider_factory(ledger, run_id)
        pages = [p for p in notion.list_all_pages() if p.get("Job Fingerprint")]

        ids = reader.list_message_ids(lookback_days)
        summary.fetched = len(ids)
        settled = ledger.settled_message_ids()
        fresh = [i for i in ids if i not in settled]
        summary.already_settled = len(ids) - len(fresh)
        msgs = sorted((reader.get_message(i) for i in fresh), key=lambda m: m.received_at)
        for msg in msgs:
            _process(msg, pages, provider, notion, dry_run, ledger, run_id, summary)
            summary.processed += 1

        logged = ledger.query("SELECT COUNT(*) AS n FROM email_events WHERE run_id = ?", (run_id,))[0]["n"]
        problems = []
        if logged != len(msgs):
            problems.append(f"INBOX CONSERVATION VIOLATED: {len(msgs)} messages looked at, {logged} rows logged")
        if summary.errors:
            problems.append(f"{len(summary.errors)} error(s); affected emails retry next run")
        if problems:
            status, note = "degraded", "; ".join(problems)[:300]
    except Exception as exc:
        status, note = "failed", f"{type(exc).__name__}: {exc}"[:300]
        raise
    finally:
        ledger.finish_run(run_id, status, note)
        ledger.close()
    return summary
