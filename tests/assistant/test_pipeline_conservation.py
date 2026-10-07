"""Whole-pipeline audit: real Stage 0 + dedup + gateway + evaluate + write, scripted AI and Notion.
Every item must be accounted for at every node, whatever happens to it."""
from datetime import UTC, datetime, timedelta

import jobai.assistant.workflows.process_job as pj
from jobai.core.config import load_career_rules, load_roles
from jobai.core.ledger.conservation import check_conservation
from jobai.core.ledger.db import Ledger
from jobai.core.ledger.events import Events
from jobai.core.telemetry.logging import RunSummary
from jobai.engine.ai.provider import LLMProvider
from jobai.engine.jobs.decisions import DecisionCache
from jobai.engine.jobs.schemas import NormalizedJob
from tests.fakes import FakeResponse, RoutedSession, ok

RULES, ROLES = load_career_rules(), load_roles()
CLASSIFY = {"role_type": "ai_ml_engineering", "role_family": "RF01", "seniority": "senior", "fit": "strong",
            "hard_blocker": False, "key_requirements": ["LLM"], "why": "core"}
REJECT = {**CLASSIFY, "role_type": "non_engineering", "fit": "no", "why": "marketing"}
STRONG = {"requirements": [{"req": "LLM", "importance": "core", "evidence": "direct", "achievement_ids": ["A05"]}],
          "blocker": False, "reason": "strong"}
WEAK = {"requirements": [{"req": "Rust", "importance": "core", "evidence": "none", "achievement_ids": []}],
        "blocker": False, "reason": "weak"}
NAMES = ("Alpha", "Bravo", "Charlie", "Delta", "Echo", "Golf", "Hotel", "India")


def job(name, *, title=None, **o):
    d = dict(
        external_job_id=name, source="greenhouse", source_company_identifier="a", company_name="Acme",
        title=title or f"{name} ML Engineer", location="Remote", workplace_type="Remote",
        description="Build LLM things.", job_url="https://x", job_fingerprint=f"greenhouse:{name}",
        description_hash=f"h-{name}", posted_at=datetime.now(UTC) - timedelta(days=2),
    )
    d.update(o)
    return NormalizedJob(**d)


class FakeNotion:
    def __init__(self, fail_on=()):
        self.fail_on, self.created, self.updated = set(fail_on), [], []

    def create_job_page(self, props):
        if props["Job Fingerprint"] in self.fail_on:
            raise RuntimeError("notion down")
        self.created.append(props["Job Fingerprint"])

    def update_job_page(self, page_id, props):
        self.updated.append(page_id)


def router(body):
    text = body["messages"][0]["content"]
    name = next(n for n in NAMES if f"{n} ML Engineer" in text)
    is_match = "checking ONE job's requirements" in text
    if name == "Delta" and not is_match:
        return ok("this is not json")  # garbage forever -> llm_error
    if name == "Echo" and not is_match:
        return ok({k: v for k, v in CLASSIFY.items() if k != "fit"})  # never valid -> llm_schema
    if is_match:
        return ok(WEAK if name == "Charlie" else STRONG)
    return ok(REJECT if name == "Bravo" else CLASSIFY)


def run_pipeline(monkeypatch, jobs, pages=(), *, ai=router, rules=RULES, notion=None, budget=None, breaker=5,
                 workers=6, rejected=(), strict=True):
    monkeypatch.setattr(pj, "AI_WORKERS", workers)
    ledger = Ledger.memory()
    run_id = ledger.start_run("discovery")
    cfg = {
        "provider": {"name": "fake", "base_url": "https://fake.invalid/v1", "api_key_env": "AIMLAPI_KEY"},
        "gateway": {"max_attempts": 3, "backoff_base_s": 0, "backoff_max_s": 0, "circuit_breaker_failures": breaker},
        "budget": {"per_run_usd": 1.0, "per_day_usd": 10.0, "max_calls_per_run": 500, **(budget or {})},
    }
    provider = LLMProvider(ledger, run_id, session=RoutedSession(ai), sleep=lambda s: None, config=cfg, usage_sink=None)
    events = Events(ledger, run_id, strict=strict)
    decisions = DecisionCache(persist=False)
    for fp, h in rejected:
        decisions.record_rejection(fp, h, "earlier verdict")
    notion = notion or FakeNotion()
    summary = RunSummary()

    events.funnel("fetch", {"normalized": len(jobs)})
    cands = pj.stage0_filter_and_dedupe(jobs, pj.DedupIndex(list(pages)), decisions, rules, ROLES, summary, events=events)
    vetted = pj.evaluate(cands, decisions, rules, summary, provider, events=events)
    pj.write_to_notion(vetted, notion, summary, events=events)
    return ledger, run_id, summary, notion, decisions


def by(ledger, node):
    return {r["item_id"].split(":")[1]: (r["disposition"], r["reason_code"])
            for r in ledger.query("SELECT item_id, disposition, reason_code FROM events WHERE node = ?", (node,))}


def test_every_item_is_accounted_for_at_every_node_across_all_dispositions(monkeypatch):
    jobs = [
        job("Stale", posted_at=datetime.now(UTC) - timedelta(days=90)),
        job("Senior", title="Staff ML Engineer"),
        job("Restricted", location="Remote (US Only)", description="US-based only. LLM."),
        job("Generic", title="Backend Software Engineer", description="Build web apps."),
        job("Alpha"), job("Alpha"),  # the same posting returned by two queries
        job("Dupid"), job("Rolefoo"), job("Progress"), job("Prev"),
        job("Bravo"), job("Charlie"), job("Delta"), job("Echo"), job("Golf"), job("Hotel"),
    ]
    pages = [
        {"Company": "Acme", "Role": "Dupid ML Engineer", "Job Fingerprint": "greenhouse:Dupid", "JD Hash": "h-Dupid",
         "Status": "Discovered", "notion_page_id": "p-dup"},
        {"Company": "Acme", "Role": "Rolefoo ML Engineer", "Job Fingerprint": "lever:other", "Status": "Discovered"},
        {"Company": "Acme", "Role": "Progress ML Engineer", "Job Fingerprint": "greenhouse:Progress", "JD Hash": "old",
         "Status": "Applied", "notion_page_id": "p-prog"},
        {"Company": "Acme", "Role": "Golf ML Engineer", "Job Fingerprint": "greenhouse:Golf", "JD Hash": "OLD",
         "Status": "Discovered", "notion_page_id": "p-golf"},
    ]
    ledger, run, summary, notion, _ = run_pipeline(
        monkeypatch, jobs, pages, rejected=[("greenhouse:Prev", "h-Prev")], notion=FakeNotion(fail_on={"greenhouse:Hotel"})
    )

    assert check_conservation(ledger, run) == []

    funnel = {r["reason_code"]: r["n"] for r in ledger.query("SELECT * FROM funnel WHERE node='stage0'")}
    assert sum(funnel.values()) == 16 and funnel["duplicate_in_run"] == 1 and funnel["stale"] == 1
    assert funnel["too_senior_title"] == 1 and funnel["location_restricted"] == 1 and funnel["passed_stage0"] == 11

    assert by(ledger, "dedupe") == {
        "Dupid": ("skipped", "duplicate_id"), "Rolefoo": ("skipped", "duplicate_role"),
        "Progress": ("skipped", "in_progress"), "Prev": ("skipped", "previously_rejected"),
        **{n: ("passed", "passed_dedupe") for n in ("Alpha", "Bravo", "Charlie", "Delta", "Echo", "Golf", "Hotel")},
    }
    assert by(ledger, "triage") == {
        "Alpha": ("passed", "approved_triage"), "Bravo": ("rejected", "rejected_role_type"),
        "Charlie": ("passed", "approved_triage"), "Delta": ("errored", "llm_error"), "Echo": ("errored", "llm_schema"),
        "Golf": ("passed", "approved_triage"), "Hotel": ("passed", "approved_triage"),
    }
    assert by(ledger, "match") == {
        "Alpha": ("passed", "approved_match"), "Charlie": ("rejected", "rejected_weak"),
        "Golf": ("passed", "approved_match"), "Hotel": ("passed", "approved_match"),
    }
    assert by(ledger, "write") == {
        "Alpha": ("passed", "written_new"), "Golf": ("passed", "written_update"), "Hotel": ("errored", "notion_error"),
    }
    assert notion.created == ["greenhouse:Alpha"] and notion.updated == ["p-golf"]


def test_budget_exhaustion_defers_items_and_conservation_still_balances(monkeypatch):
    jobs = [job(n) for n in ("Alpha", "Bravo", "Charlie", "Delta", "Echo")]
    ledger, run, summary, _, decisions = run_pipeline(
        monkeypatch, jobs, ai=lambda b: ok(CLASSIFY, cost=0.0002), budget={"per_run_usd": 0.0003}, workers=1
    )
    assert check_conservation(ledger, run) == []
    assert sorted(v for v in by(ledger, "triage").values()) == [("deferred", "llm_budget")] * 3 + [("passed", "approved_triage")] * 2
    assert {v for v in by(ledger, "match").values()} == {("deferred", "llm_budget")}
    assert by(ledger, "write") == {}
    assert not any(decisions.is_known_rejection(f"greenhouse:{n}", f"h-{n}") for n in ("Alpha", "Bravo", "Charlie", "Delta", "Echo"))


def test_the_match_cap_is_an_explicit_deferral_not_a_silent_drop(monkeypatch):
    rules = {**RULES, "ai_gates": {**RULES["ai_gates"], "max_deep_matches_per_run": 1}}
    ledger, run, _, notion, _ = run_pipeline(monkeypatch, [job("Alpha"), job("Golf"), job("Hotel")], rules=rules, workers=1)
    assert check_conservation(ledger, run) == []
    assert sorted(v for v in by(ledger, "match").values()) == [("deferred", "cap_overflow")] * 2 + [("passed", "approved_match")]
    assert len(notion.created) == 1


def test_provider_outage_records_errors_then_breaker_deferrals(monkeypatch):
    jobs = [job(n) for n in ("Alpha", "Bravo", "Charlie", "Delta", "Echo", "Golf")]
    ledger, run, _, _, _ = run_pipeline(monkeypatch, jobs, ai=lambda b: FakeResponse(500, text="down"), breaker=2, workers=1)
    assert check_conservation(ledger, run) == []
    assert sorted(v for v in by(ledger, "triage").values()) == [("deferred", "llm_circuit")] * 4 + [("errored", "llm_error")] * 2


def test_conservation_catches_a_branch_that_forgets_to_record(monkeypatch):
    """Mutation check: a pipeline change that silently drops one item's match event must be detected."""
    real_item = Events.item

    def forgetful(self, node, item_id, disposition, code, detail=None):
        if node == "match" and item_id.endswith("Charlie"):
            return  # the bug: this branch never records
        return real_item(self, node, item_id, disposition, code, detail)

    monkeypatch.setattr(Events, "item", forgetful)
    ledger, run, *_ = run_pipeline(monkeypatch, [job("Alpha"), job("Charlie")])
    violations = check_conservation(ledger, run)
    assert violations and "no match event" in violations[0] and "Charlie" in violations[0]


def test_lenient_mode_never_crashes_the_run_when_ledger_writes_fail(monkeypatch):
    monkeypatch.setattr(Ledger, "record_event", lambda self, **k: (_ for _ in ()).throw(ValueError("disk full")))
    ledger, run, summary, notion, _ = run_pipeline(monkeypatch, [job("Alpha")], strict=False)
    assert notion.created == ["greenhouse:Alpha"]  # the business outcome is unaffected
