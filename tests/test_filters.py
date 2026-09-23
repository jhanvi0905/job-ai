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
    job = make_job(posted_at=datetime.now(timezone.utc) - timedelta(days=45))
    result = apply_filters(job, CAREER_RULES, ROLES)
    assert not result.passed
    assert any("stale" in r for r in result.reasons)


def test_onsite_job_is_excluded_remote_only_policy():
    # 2026-09-22 correction: Remote only for now, even for on-site-in-India —
    # allowed_workplace_types no longer includes On-site/Hybrid at all.
    job = make_job(workplace_type="On-site", location="Bangalore, India")
    result = apply_filters(job, CAREER_RULES, ROLES)
    assert not result.passed
    assert any("not in allowed list" in r for r in result.reasons)


def test_location_eligible_onsite_logic_still_correct_if_re_enabled():
    # The On-site/Hybrid eligibility logic itself is dormant, not deleted —
    # re-adding "On-site" to career_rules.yaml should just work. Verified
    # directly here so that isn't silently untested while unused.
    from src.jobs.filters import _location_eligible

    loc_cfg = CAREER_RULES["location"]
    in_india = make_job(workplace_type="On-site", location="Bangalore, India")
    outside_india = make_job(workplace_type="On-site", location="San Francisco")
    assert _location_eligible(in_india, loc_cfg) == (True, None)
    eligible, reason = _location_eligible(outside_india, loc_cfg)
    assert not eligible and "not located in India" in reason


def test_remote_job_restricted_to_us_is_filtered():
    job = make_job(
        workplace_type="Remote",
        location="Remote (US Only)",
        description="This role is US-based and open only to candidates within the United States.",
    )
    result = apply_filters(job, CAREER_RULES, ROLES)
    assert not result.passed
    assert any("restricted" in r for r in result.reasons)


def test_remote_job_explicitly_open_to_india_passes_despite_restrictive_language():
    job = make_job(
        workplace_type="Remote",
        location="Remote - US or India",
        description="Open to candidates within the United States or India.",
    )
    result = apply_filters(job, CAREER_RULES, ROLES)
    assert result.passed


def test_remote_job_with_structured_country_from_ashby_is_respected():
    # Ashby-sourced Remote jobs carry a structured location_country — that
    # should be trusted over text-guessing (this is what caught OpenAI's
    # "US - Remote" postings that plain text-matching missed).
    job = make_job(workplace_type="Remote", location="India - Remote", location_country="India")
    result = apply_filters(job, CAREER_RULES, ROLES)
    assert result.passed

    job2 = make_job(workplace_type="Remote", location="US - Remote", location_country="United States")
    result2 = apply_filters(job2, CAREER_RULES, ROLES)
    assert not result2.passed


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


def test_too_senior_title_is_filtered():
    for title in ("Staff AI Engineer", "Director, Machine Learning", "Principal ML Engineer", "Head of AI"):
        result = apply_filters(make_job(title=title), CAREER_RULES, ROLES)
        assert not result.passed, title
        assert any("too senior" in r for r in result.reasons), title


def test_staffing_is_not_mistaken_for_staff_level():
    # whole-word match: "Staffing" must not trip the "staff" seniority rule
    result = apply_filters(make_job(title="AI Engineer, Staffing Platform"), CAREER_RULES, ROLES)
    assert result.passed


def test_role_asking_far_more_years_than_candidate_is_filtered():
    job = make_job(description="We need 10+ years of experience shipping production ML. LLM, RAG.")
    result = apply_filters(job, CAREER_RULES, ROLES)
    assert not result.passed
    assert any("yrs" in r for r in result.reasons)


def test_role_asking_within_reach_passes_and_records_years():
    job = make_job(description="4+ years of experience with LLM systems and RAG.")
    result = apply_filters(job, CAREER_RULES, ROLES)
    assert result.passed
    assert result.min_years_required == 4


def test_junior_years_cap_is_filtered():
    job = make_job(description="Ideal for 0-2 years of experience. LLM and RAG projects.")
    result = apply_filters(job, CAREER_RULES, ROLES)
    assert not result.passed


def test_generic_software_engineer_title_is_filtered():
    job = make_job(
        title="Senior Software Engineer - Backend",
        description="Our platform uses LLM, RAG and agent tooling across production AI.",
    )
    result = apply_filters(job, CAREER_RULES, ROLES)
    assert not result.passed
    assert any("no AI/ML/data signal" in r for r in result.reasons)


def test_data_analyst_title_is_filtered():
    result = apply_filters(make_job(title="Senior Data Analyst"), CAREER_RULES, ROLES)
    assert not result.passed
