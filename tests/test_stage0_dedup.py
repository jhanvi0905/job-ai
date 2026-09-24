from src.config import load_career_rules, load_roles
from src.jobs.decisions import DecisionCache
from src.ledger.db import Ledger

LEDGERS: dict = {}  # one in-memory ledger per test tmp_path, shared by caches that must 'reload'
from src.jobs.schemas import NormalizedJob
from src.telemetry.logging import RunSummary
from src.workflows.process_job import DedupIndex, stage0_filter_and_dedupe

RULES = load_career_rules()
ROLES = load_roles()


def make_job(**o) -> NormalizedJob:
    d = dict(
        external_job_id="1",
        source="himalayas",
        source_company_identifier="acme",
        company_name="Acme",
        title="Senior AI Engineer",
        location="Worldwide",
        workplace_type="Remote",
        description="We build production LLM agents with RAG and evaluations.",
        job_url="https://acme.example/1",
        job_fingerprint="himalayas:1",
        description_hash="h1",
    )
    d.update(o)
    return NormalizedJob(**d)


def cache(tmp_path) -> DecisionCache:
    return DecisionCache(LEDGERS.setdefault(tmp_path, Ledger.memory()))


def run(jobs, pages, tmp_path):
    summary = RunSummary()
    out = stage0_filter_and_dedupe(jobs, DedupIndex(pages), cache(tmp_path), RULES, ROLES, summary)
    return out, summary


def test_same_posting_from_two_queries_is_processed_once(tmp_path):
    out, s = run([make_job(), make_job()], [], tmp_path)
    assert len(out) == 1 and s.duplicates == 1


def test_same_role_from_another_source_is_a_content_duplicate(tmp_path):
    himalayas = make_job()
    greenhouse = make_job(source="greenhouse", external_job_id="99", job_fingerprint="greenhouse:99")
    out, s = run([himalayas, greenhouse], [], tmp_path)
    assert len(out) == 1
    assert s.content_duplicates == 1


def test_role_already_in_notion_under_another_source_is_skipped(tmp_path):
    page = {"Company": "Acme", "Role": "Senior AI Engineer", "Job Fingerprint": "greenhouse:99", "Status": "Discovered"}
    out, s = run([make_job()], [page], tmp_path)
    assert out == [] and s.content_duplicates == 1


def test_unchanged_page_in_notion_is_a_duplicate(tmp_path):
    page = {"Company": "Acme", "Role": "Senior AI Engineer", "Job Fingerprint": "himalayas:1",
            "JD Hash": "h1", "Status": "Discovered", "notion_page_id": "p1"}
    out, s = run([make_job()], [page], tmp_path)
    assert out == [] and s.duplicates == 1


def test_changed_description_is_re_evaluated_and_keeps_the_page(tmp_path):
    page = {"Company": "Acme", "Role": "Senior AI Engineer", "Job Fingerprint": "himalayas:1",
            "JD Hash": "OLD", "Status": "Discovered", "notion_page_id": "p1"}
    out, _ = run([make_job()], [page], tmp_path)
    assert len(out) == 1 and out[0].existing["notion_page_id"] == "p1"


def test_jobs_you_are_already_working_are_left_alone(tmp_path):
    page = {"Company": "Acme", "Role": "Senior AI Engineer", "Job Fingerprint": "himalayas:1",
            "JD Hash": "OLD", "Status": "Applied", "notion_page_id": "p1"}
    out, s = run([make_job()], [page], tmp_path)
    assert out == [] and s.in_progress_skipped == 1


def test_previously_rejected_unchanged_job_costs_no_tokens(tmp_path):
    c = cache(tmp_path)
    c.record_rejection("himalayas:1", "h1", "stage1 software_engineering_general/no")
    summary = RunSummary()
    out = stage0_filter_and_dedupe([make_job()], DedupIndex([]), c, RULES, ROLES, summary)
    assert out == [] and summary.previously_rejected == 1


def test_rejection_is_forgotten_when_the_description_changes(tmp_path):
    c = cache(tmp_path)
    c.record_rejection("himalayas:1", "OLD-HASH", "stage1 no")
    out = stage0_filter_and_dedupe([make_job()], DedupIndex([]), c, RULES, ROLES, RunSummary())
    assert len(out) == 1


def test_rejection_is_forgotten_when_the_rules_change(tmp_path):
    c = cache(tmp_path)
    c.record_rejection("himalayas:1", "h1", "stage1 no")
    c2 = DecisionCache(LEDGERS[tmp_path])
    c2.signature = "different-rules-signature"
    assert not c2.is_known_rejection("himalayas:1", "h1")


def test_stage0_makes_no_network_calls_for_filtered_jobs(tmp_path):
    junk = make_job(job_fingerprint="himalayas:2", external_job_id="2", title="Payroll Accountant")
    out, s = run([junk], [], tmp_path)
    assert out == [] and s.stale_or_filtered == 1
