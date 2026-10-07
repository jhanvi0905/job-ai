import pytest
from pydantic import ValidationError

from jobai.core.config import load_career_rules, load_roles
from jobai.engine.achievements.retrieval import retrieve_achievements
from jobai.engine.jobs.filters import apply_filters
from jobai.engine.jobs.schemas import NormalizedJob
from jobai.product.db.models import SearchPrefs
from jobai.product.services.prefs import (
    SearchPrefsModel,
    achievement_index,
    load_prefs,
    profile_from_user,
    roles_from_prefs,
    rules_from_prefs,
    rules_signature,
)


def remote_job(location: str) -> NormalizedJob:
    return NormalizedJob(
        external_job_id="1", source="greenhouse", source_company_identifier="a", company_name="Acme",
        title="Senior ML Engineer", location=location, workplace_type="Remote",
        description="Build LLM systems in Python.", job_url="https://x",
    )


def stage0(prefs: SearchPrefsModel, job: NormalizedJob):
    return apply_filters(job, rules_from_prefs(prefs), roles_from_prefs(prefs))


def test_default_prefs_match_shipped_rules():
    base, rules = load_career_rules(), rules_from_prefs(SearchPrefsModel())
    assert rules["location"]["candidate_country"] == "India"
    assert rules["experience"] == base["experience"]
    assert rules["recency"] == base["recency"]


def test_country_changes_stage0_outcome():
    canada_job = remote_job("Remote - Canada")
    india = stage0(SearchPrefsModel(countries=["India"]), canada_job)
    canada = stage0(SearchPrefsModel(countries=["Canada"]), canada_job)
    assert not india.passed and "location_restricted" in india.codes
    assert canada.passed, canada.reasons


def test_other_users_home_country_is_not_a_global_signal():
    # The shipped config treats "india" as an eligibility signal; a Canada user must not inherit it.
    rules = rules_from_prefs(SearchPrefsModel(countries=["Canada"]))
    assert "india" not in rules["location"]["eligible_signals"]
    assert "canada" in rules["location"]["eligible_signals"]
    assert "canada" not in rules["location"]["location_named_regions"]


def test_secondary_country_is_eligible():
    prefs = SearchPrefsModel(countries=["India", "Canada"])
    assert stage0(prefs, remote_job("Remote - Canada")).passed


def test_years_workplace_and_recency_overrides():
    rules = rules_from_prefs(SearchPrefsModel(total_years=8, max_age_days=7, workplace_types=["Remote", "Hybrid"],
                                              excluded_seniority=["director"]))
    assert rules["experience"]["total_years"] == 8 and rules["experience"]["max_required_years"] == 11
    assert rules["recency"]["max_age_days"] == 7
    assert rules["location"]["allowed_workplace_types"] == ["Remote", "Hybrid"]
    assert rules["seniority"]["too_senior_title_keywords"] == ["director"]
    assert rules_from_prefs(SearchPrefsModel(remote_only=True, workplace_types=["Hybrid"]))["location"]["allowed_workplace_types"] == ["Remote"]


def test_base_config_is_not_mutated():
    before = load_career_rules()["location"]["candidate_country"]
    rules_from_prefs(SearchPrefsModel(countries=["Canada"]))
    assert load_career_rules()["location"]["candidate_country"] == before


def test_roles_restricted_to_chosen_families():
    assert list(roles_from_prefs(SearchPrefsModel(role_families=["RF01"]))["role_families"]) == ["RF01"]
    assert roles_from_prefs(SearchPrefsModel())["role_families"] == load_roles()["role_families"]
    # Unknown ids are a validation error now (422 at the API), never a silent "all".
    with pytest.raises(ValidationError):
        SearchPrefsModel(role_families=["nope"])


def test_load_prefs_defaults_and_roundtrip(session, make_user):
    user = make_user("a@x.com")
    assert load_prefs(session, user.id) == SearchPrefsModel()
    session.add(SearchPrefs(user_id=user.id, data={"countries": ["Canada"], "total_years": 5}))
    session.commit()
    assert load_prefs(session, user.id).countries == ["Canada"]


def test_achievement_index_shape_and_retrieval(session, make_user, add_achievement):
    user = make_user("a@x.com")
    row = add_achievement(user.id, skills=["Python", "RAG"], system_patterns=["retrieval"])
    index = achievement_index(session, user.id)
    assert index[0]["id"] == f"A{row.id}" and index[0]["title"] == row.title
    assert set(index[0]) >= {"id", "title", "summary", "role_families", "skills", "system_patterns",
                             "seniority_signals", "business_signals", "leadership_signals"}
    hits = retrieve_achievements("RF02", ["python"], index=index)
    assert [h.id for h in hits] == [index[0]["id"]]


def test_profile_from_user_is_built_from_own_rows_only(session, make_user, add_achievement):
    a, b = make_user("a@x.com"), make_user("b@x.com")
    add_achievement(a.id, title="Alpha project", skills=["Rust"])
    add_achievement(b.id, title="Beta project", skills=["COBOL"])
    profile = profile_from_user(session, a.id)
    assert "Alpha project" in profile["summary"] and "Beta" not in profile["summary"]
    assert "Rust" in profile["baseline_skills"] and "COBOL" not in profile["baseline_skills"]


def test_rules_signature_changes_with_inputs():
    models = {"routing": {"classify_job": {"m": 1}, "analyse_match": {"m": 2}}}
    prefs = SearchPrefsModel()
    rules, profile = rules_from_prefs(prefs), {"summary": "s", "baseline_skills": "b"}
    base = rules_signature(rules, profile, models)
    assert base == rules_signature(rules_from_prefs(prefs), dict(profile), models)
    assert base != rules_signature(rules_from_prefs(SearchPrefsModel(countries=["Canada"])), profile, models)
    assert base != rules_signature(rules, {**profile, "summary": "t"}, models)
    assert base != rules_signature(rules, profile, {"routing": {"classify_job": {"m": 9}, "analyse_match": {"m": 2}}})
