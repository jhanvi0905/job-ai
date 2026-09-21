from datetime import datetime, timedelta, timezone

from src.config import load_career_rules, load_roles
from src.jobs.filters import apply_filters
from src.jobs.schemas import NormalizedJob

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
        employment_type=None,
        description="We build production LLM agents with RAG and evaluations.",
        posted_at=datetime.now(timezone.utc) - timedelta(days=2),
        job_url="https://acme.example/jobs/1",
    )
    defaults.update(overrides)
    return NormalizedJob(**defaults)


def test_relevant_remote_senior_ai_job_passes():
    job = make_job()
    result = apply_filters(job, CAREER_RULES, ROLES)
    assert result.passed
    assert result.keyword_score > 0


def test_stale_job_is_filtered():
    job = make_job(posted_at=datetime.now(timezone.utc) - timedelta(days=30))
    result = apply_filters(job, CAREER_RULES, ROLES)
    assert not result.passed
    assert any("stale" in r for r in result.reasons)


def test_onsite_job_is_filtered():
    job = make_job(workplace_type="On-site", location="San Francisco")
    result = apply_filters(job, CAREER_RULES, ROLES)
    assert not result.passed
    assert any("workplace_type" in r for r in result.reasons)


def test_internship_title_is_filtered():
    job = make_job(title="AI Engineering Intern")
    result = apply_filters(job, CAREER_RULES, ROLES)
    assert not result.passed
    assert any("seniority exclusion" in r for r in result.reasons)


def test_irrelevant_job_with_no_signal_is_filtered():
    job = make_job(
        title="Warehouse Associate",
        description="Lift boxes and operate a forklift in our distribution center.",
    )
    result = apply_filters(job, CAREER_RULES, ROLES)
    assert not result.passed
    assert any("no title-family match" in r for r in result.reasons)


def test_unknown_location_passes_through_by_default():
    job = make_job(workplace_type="Unknown", location=None)
    result = apply_filters(job, CAREER_RULES, ROLES)
    # Passes through Stage 0 (not auto-rejected) since unknown_location_passes_through
    # is true — relevance is still gated by title/keyword signal.
    assert result.passed
