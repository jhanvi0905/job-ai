import pytest
from pydantic import ValidationError

from jobai.engine.jobs.schemas import JobClassification, JobMatch, NormalizedJob


def test_normalized_job_requires_job_url():
    with pytest.raises(ValidationError):
        NormalizedJob(
            external_job_id="1",
            source="greenhouse",
            source_company_identifier="acme",
            company_name="Acme",
            title="AI Engineer",
        )


def test_job_classification_rejects_missing_relevant():
    with pytest.raises(ValidationError):
        JobClassification()  # type: ignore[call-arg]


def test_job_match_validates_fit_band_enum():
    with pytest.raises(ValidationError):
        JobMatch(
            fit_band="amazing",  # not a valid literal
            priority="P1",
            reason="test",
        )


def test_job_match_accepts_valid_payload():
    match = JobMatch(
        fit_band="strong",
        priority="P1",
        matched_achievements=[{"id": "A01", "strength": "strong", "supports": ["production AI"]}],
        strong_evidence=["production AI"],
        gaps=["PyTorch training depth"],
        reason="Strong overlap with production AI ownership.",
        recommended_action="review",
    )
    assert match.matched_achievements[0].id == "A01"
