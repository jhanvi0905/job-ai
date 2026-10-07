"""Every Stage 0 rule must map to a real reason code — never the 'other' bucket."""
from datetime import UTC, datetime, timedelta

import pytest

from jobai.core.config import load_career_rules, load_roles
from jobai.core.ledger.codes import NODE_REASONS
from jobai.engine.jobs.filters import apply_filters, code_for_reason
from jobai.engine.jobs.schemas import NormalizedJob

RULES, ROLES = load_career_rules(), load_roles()


def job(**o) -> NormalizedJob:
    d = dict(
        external_job_id="1", source="greenhouse", source_company_identifier="a", company_name="Acme",
        title="Senior AI Engineer", location="Remote", workplace_type="Remote",
        description="We build production LLM agents with RAG.", job_url="https://x",
        posted_at=datetime.now(UTC) - timedelta(days=2),
    )
    d.update(o)
    return NormalizedJob(**d)


SCENARIOS = {
    "stale": job(posted_at=datetime.now(UTC) - timedelta(days=90)),
    "workplace_type": job(workplace_type="On-site", location="Bangalore, India"),
    "location_restricted": job(location="Remote (US Only)", description="US-based only. LLM RAG."),
    "junior_title": job(title="AI Engineering Intern"),
    "too_senior_title": job(title="Staff AI Engineer"),
    "years_too_high": job(description="Requires 10+ years of experience. LLM and RAG."),
    "junior_ask": job(description="Ideal for 0-2 years of experience. LLM RAG."),
    "hard_exclusion": job(title="Payroll Accountant"),
    "no_signal": job(title="Warehouse Associate", description="Lift boxes."),
    "analyst_title": job(title="Senior Data Analyst"),
    "generic_title": job(title="Senior Software Engineer - Backend", description="LLM RAG agents."),
}


@pytest.mark.parametrize("expected,j", SCENARIOS.items())
def test_each_rule_reports_its_own_code(expected, j):
    result = apply_filters(j, RULES, ROLES)
    assert not result.passed
    assert expected in result.codes
    assert "stage0_other" not in result.codes


def test_passing_job_has_no_codes():
    assert apply_filters(job(), RULES, ROLES).codes == []


def test_codes_align_with_reasons_and_primary_is_the_first_rule_that_fired():
    result = apply_filters(job(title="Staff AI Engineer", posted_at=datetime.now(UTC) - timedelta(days=90)), RULES, ROLES)
    assert len(result.codes) == len(result.reasons)
    assert result.codes[0] == "stale"  # checked before seniority


def test_unknown_message_falls_to_other_rather_than_crashing():
    assert code_for_reason("some brand new rule") == "stage0_other"


def test_every_code_the_filters_can_emit_is_legal_at_the_stage0_node():
    from jobai.engine.jobs.filters import _REASON_CODES

    for _, code in _REASON_CODES:
        assert code in NODE_REASONS["stage0"], code
