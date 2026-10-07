"""Classifier and matcher exercised end to end THROUGH the gateway, against scripted
responses: real prompts, real validation, real ledger — no network, no cost."""
import pytest

from jobai.core.ledger.db import Ledger
from jobai.engine.achievements.retrieval import retrieve_achievements
from jobai.engine.ai.classifier import classify_job
from jobai.engine.ai.matcher import analyse_match
from jobai.engine.ai.provider import LLMProvider, SchemaError
from jobai.engine.jobs.schemas import NormalizedJob
from tests.fakes import FakeSession, ok

CFG = {
    "provider": {"name": "fake", "base_url": "https://fake.invalid/v1", "api_key_env": "AIMLAPI_KEY"},
    "gateway": {"max_attempts": 3, "backoff_base_s": 0.0, "backoff_max_s": 0.0, "circuit_breaker_failures": 5},
}

JOB = NormalizedJob(
    external_job_id="1", source="greenhouse", source_company_identifier="acme", company_name="Acme",
    title="Senior ML Engineer", location="Remote", workplace_type="Remote",
    description="Build LLM systems. 5+ years of experience required. " + "x" * 5000,
    job_url="https://x", job_fingerprint="greenhouse:1", description_hash="h1",
)

GOOD_CLASSIFICATION = {
    "role_type": "ai_ml_engineering", "role_family": "RF01", "seniority": "senior",
    "fit": "strong", "hard_blocker": False, "key_requirements": ["LLM systems"], "why": "core LLM role",
}
GOOD_MATCH = {
    "requirements": [
        {"req": "LLM systems", "importance": "core", "evidence": "direct", "achievement_ids": ["A05"]},
        {"req": "RAG", "importance": "core", "evidence": "direct", "achievement_ids": ["A01"]},
    ],
    "blocker": False, "reason": "Strong LLM and RAG evidence.",
}


def setup(script):
    ledger = Ledger.memory()
    run_id = ledger.start_run("test")
    session = FakeSession(script)
    provider = LLMProvider(ledger, run_id, session=session, sleep=lambda s: None, config=CFG, usage_sink=None)
    return provider, session, ledger


def calls(ledger):
    return ledger.query("SELECT * FROM llm_calls ORDER BY call_id")


# ---------------------------------------------------------------- classifier
def test_classifier_result_is_recorded_with_prompt_version_and_context():
    provider, session, ledger = setup([ok(GOOD_CLASSIFICATION)])
    result = classify_job(JOB, provider)
    assert result.relevant and result.role_type == "ai_ml_engineering"
    (row,) = calls(ledger)
    assert row["prompt_version"] == "classify_job_v2" and row["node"] == "classify_job"
    assert '"jd_truncated": true' in row["context_json"] and '"jd_chars_sent": 4000' in row["context_json"]


def test_years_are_enforced_in_code_even_if_the_model_says_strong():
    # JD asks 5+ yrs, candidate has 3 -> gap 2 -> capped to plausible regardless of the model
    provider, _, _ = setup([ok({**GOOD_CLASSIFICATION, "fit": "strong"})])
    result = classify_job(JOB, provider)
    assert result.fit == "plausible" and result.min_years_required == 5


def test_the_model_never_sees_the_candidates_years():
    provider, session, _ = setup([ok(GOOD_CLASSIFICATION)])
    classify_job(JOB, provider)
    prompt = session.requests[0]["messages"][0]["content"]
    assert "years of experience: ~" not in prompt.lower()
    assert "candidate years" not in prompt.lower()


def test_missing_verdict_field_is_repaired_once_not_read_as_a_rejection():
    incomplete = {k: v for k, v in GOOD_CLASSIFICATION.items() if k != "fit"}
    provider, session, ledger = setup([ok(incomplete), ok(GOOD_CLASSIFICATION)])
    result = classify_job(JOB, provider)
    assert result.fit is not None
    assert [r["outcome"] for r in calls(ledger)] == ["schema_invalid", "ok"]
    assert "missing required field(s): fit" in session.requests[1]["messages"][-1]["content"]


def test_invalid_enum_is_a_schema_error_after_one_repair_and_never_silently_scored():
    provider, session, ledger = setup([ok({**GOOD_CLASSIFICATION, "fit": "amazing"}), ok({**GOOD_CLASSIFICATION, "fit": "great"})])
    with pytest.raises(SchemaError):
        classify_job(JOB, provider)
    assert session.calls == 2


# ------------------------------------------------------------------- matcher
def test_matcher_scores_from_requirement_judgments_and_records_evidence_ids():
    provider, _, ledger = setup([ok(GOOD_MATCH)])
    evidence = retrieve_achievements("RF01", ["LLM systems", "RAG"])
    match = analyse_match(JOB, ["LLM systems"], evidence, provider)
    assert match.fit_band == "strong" and match.priority == "P1"
    (row,) = calls(ledger)
    assert row["prompt_version"] == "analyse_match_v3"
    assert all(a.id in row["context_json"] for a in evidence)


def test_empty_requirements_are_repaired_instead_of_scored_as_weak():
    provider, session, ledger = setup([ok({"requirements": [], "reason": "?"}), ok(GOOD_MATCH)])
    match = analyse_match(JOB, [], retrieve_achievements("RF01", ["x"]), provider)
    assert match.fit_band == "strong"
    assert [r["outcome"] for r in calls(ledger)] == ["schema_invalid", "ok"]


def test_bad_evidence_label_is_repaired():
    bad = {"requirements": [{"req": "x", "importance": "core", "evidence": "sort of", "achievement_ids": []}], "reason": "r"}
    provider, session, _ = setup([ok(bad), ok(GOOD_MATCH)])
    analyse_match(JOB, [], retrieve_achievements("RF01", ["x"]), provider)
    assert "evidence must be direct|adjacent|none" in session.requests[1]["messages"][-1]["content"]


def test_a_persistently_broken_matcher_raises_rather_than_rejecting_the_job():
    provider, _, _ = setup([ok({"requirements": []}), ok({"requirements": []})])
    with pytest.raises(SchemaError):
        analyse_match(JOB, [], retrieve_achievements("RF01", ["x"]), provider)
