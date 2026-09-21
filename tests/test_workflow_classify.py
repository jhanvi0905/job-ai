from unittest.mock import patch

from src.jobs.schemas import JobClassification, NormalizedJob
from src.telemetry.logging import RunSummary
from src.workflows.process_job import classify_survivors

JOB = NormalizedJob(
    external_job_id="1",
    source="greenhouse",
    source_company_identifier="acme",
    company_name="Acme",
    title="Senior Software Engineer",
    location="Bengaluru, India",
    workplace_type="Remote",
    description="Build distributed systems in Java and Scala.",
    job_url="https://acme.example/jobs/1",
    job_fingerprint="greenhouse:1",
    description_hash="deadbeef",
)


def test_relevant_job_survives_with_classification_attached():
    classification = JobClassification(
        role_family="RF03", seniority="Senior", relevant=True, hard_blocker=False,
        key_requirements=["distributed systems"],
    )
    with patch("src.workflows.process_job.classify_job", return_value=classification):
        summary = RunSummary()
        result = classify_survivors([(JOB, None)], summary)
    assert len(result) == 1
    assert result[0][2] is classification
    assert summary.classified == 1


def test_irrelevant_job_is_excluded():
    classification = JobClassification(
        role_family=None, seniority=None, relevant=False, hard_blocker=False, key_requirements=[],
    )
    with patch("src.workflows.process_job.classify_job", return_value=classification):
        summary = RunSummary()
        result = classify_survivors([(JOB, None)], summary)
    assert result == []


def test_hard_blocker_job_is_excluded_even_if_relevant():
    classification = JobClassification(
        role_family="RF03", seniority="Senior", relevant=True, hard_blocker=True,
        hard_blocker_reason="requires US citizenship", key_requirements=[],
    )
    with patch("src.workflows.process_job.classify_job", return_value=classification):
        summary = RunSummary()
        result = classify_survivors([(JOB, None)], summary)
    assert result == []


def test_classification_failure_fails_open_not_dropped():
    with patch("src.workflows.process_job.classify_job", side_effect=RuntimeError("API down")):
        summary = RunSummary()
        result = classify_survivors([(JOB, None)], summary)
    assert len(result) == 1
    assert result[0][2] is None  # unclassified, but still passed through
    assert len(summary.ai_errors) == 1
