from unittest.mock import MagicMock

from src.config import load_career_rules, load_roles
from src.jobs.schemas import NormalizedJob
from src.telemetry.logging import RunSummary
from src.workflows.process_job import dedupe_and_filter

CAREER_RULES = load_career_rules()
ROLES = load_roles()


def make_job(**overrides) -> NormalizedJob:
    defaults = dict(
        external_job_id="1",
        source="greenhouse",
        source_company_identifier="acme",
        company_name="Acme",
        title="Senior AI Engineer",
        location="Remote",
        workplace_type="Remote",
        description="We build production LLM agents with RAG and evaluations.",
        job_url="https://acme.example/jobs/1",
        job_fingerprint="greenhouse:1",
        description_hash="hash1",
    )
    defaults.update(overrides)
    return NormalizedJob(**defaults)


def test_notion_is_never_queried_for_jobs_that_fail_stage0_filtering():
    """Regression test: an earlier version called Notion for every RAW job
    (thousands) instead of only Stage-0 survivors (tens), making a single run
    take 20+ minutes of pure network wait. This must never regress."""
    relevant_job = make_job(external_job_id="1", job_fingerprint="greenhouse:1")
    irrelevant_job = make_job(
        external_job_id="2",
        job_fingerprint="greenhouse:2",
        title="Payroll Accountant",
        description="Manage payroll and accounting operations.",
    )

    notion = MagicMock()
    notion.find_by_fingerprint.return_value = None

    summary = RunSummary()
    survivors = dedupe_and_filter([relevant_job, irrelevant_job], notion, CAREER_RULES, ROLES, summary)

    # Only the job that survives Stage 0 filtering should ever trigger a
    # Notion call — the filtered-out one must never reach the network.
    assert notion.find_by_fingerprint.call_count == 1
    notion.find_by_fingerprint.assert_called_once_with("greenhouse:1")
    assert len(survivors) == 1
    assert survivors[0][0].external_job_id == "1"
