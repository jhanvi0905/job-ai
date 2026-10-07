from unittest.mock import MagicMock, patch

from jobai.assistant.workflows.process_job import Candidate, evaluate
from jobai.core.config import load_career_rules
from jobai.core.telemetry.logging import RunSummary
from jobai.engine.jobs.decisions import DecisionCache
from jobai.engine.jobs.schemas import JobClassification, JobMatch, NormalizedJob

RULES = load_career_rules()


def job(i="1") -> NormalizedJob:
    return NormalizedJob(
        external_job_id=i, source="greenhouse", source_company_identifier="acme", company_name="Acme",
        title="Senior ML Engineer", location="Remote", workplace_type="Remote",
        description="Build models.", job_url="https://x", job_fingerprint=f"greenhouse:{i}",
        description_hash=f"h{i}",
    )


def cls(relevant=True, **o) -> JobClassification:
    d = dict(role_family="RF02", seniority="senior", role_type="ai_ml_engineering", fit="strong",
             relevant=relevant, key_requirements=["ML"], why="good")
    d.update(o)
    return JobClassification(**d)


def match(fit="strong", action="review") -> JobMatch:
    return JobMatch(fit_band=fit, priority="P1", reason="ok", recommended_action=action)


def ev(tmp_path, candidates, **patches):
    summary = RunSummary()
    decisions = DecisionCache()
    with patch("jobai.assistant.workflows.process_job.classify_job", **patches.get("classify", {"return_value": cls()})), \
         patch("jobai.assistant.workflows.process_job.analyse_match", **patches.get("match", {"return_value": match()})), \
         patch("jobai.assistant.workflows.process_job.retrieve_achievements", return_value=[]):
        out = evaluate(candidates, decisions, RULES, summary, provider=MagicMock())
    return out, summary, decisions


def test_approved_job_passes_both_gates(tmp_path):
    out, s, _ = ev(tmp_path, [Candidate(job(), None)])
    assert len(out) == 1 and out[0].match.fit_band == "strong"
    assert s.classified == 1 and s.deeply_analysed == 1


def test_stage1_rejection_is_not_written_and_is_remembered(tmp_path):
    out, s, d = ev(tmp_path, [Candidate(job(), None)], classify={"return_value": cls(relevant=False, fit="no")})
    assert out == [] and s.ai_rejected == 1 and s.deeply_analysed == 0
    assert d.is_known_rejection("greenhouse:1", "h1")


def test_weak_deep_match_is_dropped_and_remembered(tmp_path):
    out, s, d = ev(tmp_path, [Candidate(job(), None)], match={"return_value": match(fit="weak", action="reject")})
    assert out == [] and s.match_rejected == 1
    assert d.is_known_rejection("greenhouse:1", "h1")


def test_plausible_deep_match_passes(tmp_path):
    out, _, _ = ev(tmp_path, [Candidate(job(), None)], match={"return_value": match(fit="plausible")})
    assert len(out) == 1


def test_ai_outage_fails_closed_not_open_and_is_retried_next_run(tmp_path):
    out, s, d = ev(tmp_path, [Candidate(job(), None)], classify={"side_effect": RuntimeError("down")})
    assert out == []  # never written unvetted
    assert len(s.ai_errors) == 1
    assert not d.is_known_rejection("greenhouse:1", "h1")  # not remembered -> retried


def test_nothing_to_evaluate_makes_no_ai_calls(tmp_path):
    out, s, _ = ev(tmp_path, [])
    assert out == [] and s.classified == 0


def test_classifier_cannot_wave_through_a_disallowed_role_type():
    from jobai.engine.ai.classifier import _is_relevant

    gates = RULES["ai_gates"]
    assert _is_relevant({"role_type": "ai_ml_engineering", "fit": "strong"}, gates)
    assert not _is_relevant({"role_type": "non_engineering", "fit": "strong"}, gates)
    assert not _is_relevant({"role_type": "software_engineering_general", "fit": "strong"}, gates)
    assert not _is_relevant({"role_type": "data_engineering", "fit": "weak"}, gates)
    assert not _is_relevant({"role_type": "data_engineering", "fit": "strong", "hard_blocker": True}, gates)


def test_years_cap_is_enforced_in_code_not_left_to_the_model():
    from jobai.engine.ai.classifier import cap_fit_by_years

    C = 3
    assert cap_fit_by_years("strong", 4, C) == "strong"      # within 1 year: no penalty
    assert cap_fit_by_years("strong", 3, C) == "strong"
    assert cap_fit_by_years("strong", 5, C) == "plausible"   # 2 above: stretch
    assert cap_fit_by_years("strong", 6, C) == "plausible"
    assert cap_fit_by_years("plausible", 7, C) == "weak"     # 4 above: long shot
    assert cap_fit_by_years("weak", 5, C) == "weak"          # never raises a fit
    assert cap_fit_by_years("strong", None, C) == "strong"   # no stated years: untouched


def test_p1_requires_both_stages_to_agree(tmp_path):
    # Stage 1 says only plausible; Stage 3 coverage says strong -> final is plausible / P2
    out, _, _ = ev(
        tmp_path,
        [Candidate(job(), None)],
        classify={"return_value": cls(fit="plausible")},
        match={"return_value": match(fit="strong")},
    )
    assert out[0].match.fit_band == "plausible" and out[0].match.priority == "P2"


def test_both_stages_strong_gives_p1(tmp_path):
    out, _, _ = ev(tmp_path, [Candidate(job(), None)])
    assert out[0].match.fit_band == "strong" and out[0].match.priority == "P1"
