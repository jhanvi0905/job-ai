"""End-to-end inbox run with a fake mailbox, fake Notion and a scripted model. Zero cost."""
from datetime import datetime, timedelta, timezone

import pytest

import src.workflows.inbox as ib
from src.ai.provider import LLMProvider
from src.inbox.gmail import Message
from src.ledger.db import Ledger
from tests.fakes import RoutedSession, ok

T0 = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)


def msg(i, sender, domain, subject, snippet="", minutes=0, name=None):
    return Message(id=f"m{i}", thread_id=f"t{i}", sender_name=name if name is not None else sender,
                   sender_email=f"noreply@{domain}", subject=subject, snippet=snippet, received_at=T0 + timedelta(minutes=minutes))


class FakeReader:
    def __init__(self, msgs):
        self.msgs = {m.id: m for m in msgs}
        self.fetched = []

    def list_message_ids(self, days):
        return list(self.msgs)

    def get_message(self, mid):
        self.fetched.append(mid)
        return self.msgs[mid]


class FakeNotion:
    def __init__(self, pages, fail=False):
        self.pages, self.updates, self.fail = pages, [], fail

    def list_all_pages(self):
        return [dict(p) for p in self.pages]

    def update_job_page(self, page_id, props):
        if self.fail:
            raise RuntimeError("notion down")
        self.updates.append((page_id, props))


def pg(company, role, status="Discovered", **kw):
    return {"Company": company, "Role": role, "Status": status, "Job Fingerprint": f"fp-{company}-{role}",
            "notion_page_id": f"page-{company}-{role}", **kw}


CFG = {
    "provider": {"name": "fake", "base_url": "https://fake.invalid/v1", "api_key_env": "AIMLAPI_KEY"},
    "gateway": {"max_attempts": 1, "backoff_base_s": 0, "backoff_max_s": 0, "circuit_breaker_failures": 5},
    "budget": {"per_run_usd": 1.0, "per_day_usd": 10.0, "max_calls_per_run": 50},
}


def factory(router):
    box = {}

    def make(ledger, run_id):
        box["session"] = RoutedSession(router)
        return LLMProvider(ledger, run_id, session=box["session"], sleep=lambda s: None, config=CFG, usage_sink=None)

    make.box = box
    return make


NO_MODEL = factory(lambda body: (_ for _ in ()).throw(AssertionError("the model must not be called here")))


def go(msgs, pages, *, dry=False, fac=NO_MODEL, notion=None):
    notion = notion or FakeNotion(pages)
    summary = ib.run(dry_run=dry, reader=FakeReader(msgs), notion=notion, provider_factory=fac)
    ledger = Ledger()
    return summary, notion, ledger


def events(ledger):
    return {r["message_id"]: r for r in ledger.query("SELECT * FROM email_events")}


def test_a_confirmation_moves_the_job_to_applied_with_the_email_date_and_a_note():
    s, notion, ledger = go([msg(1, "Cummins", "greenhouse-mail.io", "Thank you for applying to Cummins", "We received your application")],
                           [pg("Cummins", "Data Engineer")])
    (page_id, props), = notion.updates
    assert page_id == "page-Cummins-Data Engineer"
    assert props["Status"] == "Applied" and props["Applied Date"] == "2026-09-20" and props["Notes"].startswith("Auto: confirmation email")
    e = events(ledger)["m1"]
    assert (e["reason_code"], e["from_status"], e["to_status"], e["method"], e["match_method"]) == ("matched_updated", "Discovered", "Applied", "rules", "company")
    assert ledger.query("SELECT status FROM runs")[0]["status"] == "ok"
    assert s.by_reason == {"matched_updated": 1}


def test_your_own_notes_and_applied_date_are_never_overwritten():
    s, notion, _ = go([msg(1, "Cummins", "x.io", "Thank you for applying to Cummins")],
                      [pg("Cummins", "Data Engineer", Notes="my own note", **{"Applied Date": "2026-09-01"})])
    props = notion.updates[0][1]
    assert "Notes" not in props and "Applied Date" not in props and props["Status"] == "Applied"


def test_every_kind_of_non_update_is_counted_with_its_own_reason_and_costs_no_tokens():
    pages = [pg("Cummins", "Data Engineer", "Applied"), pg("Featherless AI", "ML A", "Discovered"), pg("Featherless AI", "ML B", "Discovered"),
             pg("Acme", "Engineer", "Offer")]
    mails = [
        msg(1, "Newsletter", "news.com", "Weekly digest", "career tips"),                                    # not job mail
        msg(2, "Zzz Corp", "zzz.com", "Interview invitation", "please schedule a call"),                       # no pipeline company
        msg(3, "Featherless AI", "x.io", "Thanks for applying", "We received your application"),               # ambiguous
        msg(4, "Cummins", "x.io", "Thank you for applying", "We received your application"),                   # already Applied
        msg(5, "Acme", "x.io", "Update", "Unfortunately we will not be moving forward"),                       # Offer -> protected
        msg(6, "Cummins", "x.io", "Great news", "Something else entirely about cummins"),                     # rules can't, model called? -> see below
    ]
    # message 6 has no pattern hit AND is not from an ATS => prefilter drops it (no tokens)
    s, notion, ledger = go(mails, pages)
    got = {k: v["reason_code"] for k, v in events(ledger).items()}
    assert got == {"m1": "not_application_mail", "m2": "no_company_match", "m3": "ambiguous_match", "m4": "no_change",
                   "m5": "blocked_protected", "m6": "not_application_mail"}
    assert notion.updates == []


def test_an_unclear_email_goes_to_the_model_once_and_its_answer_is_applied():
    fac = factory(lambda body: ok({"class": "interview_request", "confidence": 0.93, "why": "wants a call"}))
    m = msg(1, "Cummins", "greenhouse-mail.io", "Next steps", "Hi, are you free this week?")  # ATS sender, no rule hit
    s, notion, ledger = go([m], [pg("Cummins", "Data Engineer", "Applied")], fac=fac)
    assert fac.box["session"].calls == 1
    e = events(ledger)["m1"]
    assert (e["method"], e["classification"], e["to_status"]) == ("llm", "interview_request", "Interview")
    assert notion.updates[0][1]["Status"] == "Interview"
    prompt = fac.box["session"].requests[0]["messages"][0]["content"]
    assert "Are you free" in prompt or "are you free" in prompt


def test_a_low_confidence_model_answer_takes_no_action():
    fac = factory(lambda body: ok({"class": "rejection", "confidence": 0.4, "why": "unclear"}))
    s, notion, ledger = go([msg(1, "Cummins", "greenhouse-mail.io", "Update", "hmm")], [pg("Cummins", "DE", "Applied")], fac=fac)
    assert notion.updates == [] and events(ledger)["m1"]["reason_code"] == "low_confidence"


def test_a_model_failure_is_recorded_retried_next_run_and_marks_the_run_degraded():
    calls = {"n": 0}

    def router(body):
        calls["n"] += 1
        from tests.fakes import FakeResponse
        return FakeResponse(500, {"error": "boom"}) if calls["n"] == 1 else ok({"class": "confirmation", "confidence": 0.9, "why": "x"})

    fac = factory(router)
    mails = [msg(1, "Cummins", "greenhouse-mail.io", "Update", "hello")]
    pages = [pg("Cummins", "DE")]
    s1, n1, ledger = go(mails, pages, fac=fac)
    assert events(ledger)["m1"]["reason_code"] == "llm_error" and s1.errors
    assert ledger.query("SELECT status, note FROM runs ORDER BY started_at LIMIT 1")[0]["status"] == "degraded"
    s2, n2, ledger = go(mails, pages, fac=fac)  # second run retries the same message
    assert n2.updates and n2.updates[0][1]["Status"] == "Applied"
    assert ledger.query("SELECT COUNT(*) n FROM email_events WHERE message_id='m1'")[0]["n"] == 2


def test_a_notion_failure_is_retried_next_run_and_nothing_is_double_counted():
    mails = [msg(1, "Cummins", "x.io", "Thank you for applying", "We received your application")]
    pages = [pg("Cummins", "DE")]
    s1, _, ledger = go(mails, pages, notion=FakeNotion(pages, fail=True))
    assert events(ledger)["m1"]["reason_code"] == "notion_error" and s1.errors
    s2, n2, ledger = go(mails, pages)
    assert len(n2.updates) == 1


def test_a_settled_message_is_never_reprocessed_or_refetched():
    mails = [msg(1, "Cummins", "x.io", "Thank you for applying", "We received your application")]
    pages = [pg("Cummins", "DE")]
    go(mails, pages)
    reader = FakeReader(mails)
    notion = FakeNotion(pages)
    s = ib.run(reader=reader, notion=notion, provider_factory=NO_MODEL)
    assert reader.fetched == [] and notion.updates == [] and s.already_settled == 1 and s.processed == 0


def test_a_dry_run_writes_nothing_to_notion_and_does_not_make_the_real_run_skip_the_mail():
    mails = [msg(1, "Cummins", "x.io", "Thank you for applying", "We received your application")]
    pages = [pg("Cummins", "DE")]
    s, notion, ledger = go(mails, pages, dry=True)
    assert notion.updates == [] and s.updates and ledger.query("SELECT graph FROM runs")[0]["graph"] == "inbox-dry"
    assert events(ledger)["m1"]["reason_code"] == "matched_updated"  # analysable...
    s2, n2, _ = go(mails, pages)                                       # ...but the live run still does the work
    assert len(n2.updates) == 1


def test_emails_are_applied_oldest_first_so_a_thread_ends_at_the_right_status():
    mails = [
        msg(1, "Cummins", "x.io", "Interview invitation", "please schedule an interview with the team", minutes=60),
        msg(2, "Cummins", "x.io", "Thank you for applying", "We received your application", minutes=0),  # older, higher id
    ]
    s, notion, _ = go(mails, [pg("Cummins", "DE")])
    assert [u[1]["Status"] for u in notion.updates] == ["Applied", "Interview"]


def test_the_run_audits_its_own_books():
    mails = [msg(i, "News", "n.com", "digest") for i in range(5)]
    s, _, ledger = go(mails, [])
    assert s.processed == 5 and ledger.query("SELECT COUNT(*) n FROM email_events")[0]["n"] == 5
    assert ledger.query("SELECT status FROM runs")[0]["status"] == "ok"


def test_a_gmail_auth_failure_fails_the_run_loudly():
    from src.inbox.gmail import GmailAuthError

    class Broken:
        def list_message_ids(self, d):
            raise GmailAuthError("revoked")

    with pytest.raises(GmailAuthError):
        ib.run(reader=Broken(), notion=FakeNotion([]), provider_factory=NO_MODEL)
    ledger = Ledger()
    r = ledger.query("SELECT status, note FROM runs")[0]
    assert r["status"] == "failed" and "revoked" in r["note"]
