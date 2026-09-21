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
        source="himalayas",
        source_company_identifier="acme",
        company_name="Acme",
        title="Senior AI Engineer",
        location="Worldwide",
        workplace_type="Remote",
        description="We build production LLM agents with RAG and evaluations.",
        job_url="https://acme.example/jobs/1",
        job_fingerprint="himalayas:https://himalayas.app/companies/acme/jobs/ai-engineer",
        description_hash="hash1",
    )
    defaults.update(overrides)
    return NormalizedJob(**defaults)


def test_same_job_returned_by_two_queries_is_only_processed_once():
    """Regression test: Himalayas can return the identical job from two
    different configured queries in the same run (e.g. matches both an
    India-specific and a worldwide search). This must not create two Notion
    pages or trigger two AI classification calls for one job."""
    same_job_from_query_a = make_job()
    same_job_from_query_b = make_job()  # identical fingerprint, different Python object

    notion = MagicMock()
    notion.find_by_fingerprint.return_value = None  # neither exists in Notion yet

    summary = RunSummary()
    survivors = dedupe_and_filter(
        [same_job_from_query_a, same_job_from_query_b], notion, CAREER_RULES, ROLES, summary
    )

    assert len(survivors) == 1
    assert notion.find_by_fingerprint.call_count == 1
    assert summary.duplicates == 1
    assert summary.new_candidates == 1
