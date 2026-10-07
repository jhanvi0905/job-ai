from unittest.mock import MagicMock, patch

from jobai.engine.sources.greenhouse import GreenhouseSource
from jobai.engine.sources.lever import LeverSource

GREENHOUSE_FIXTURE = {
    "jobs": [
        {
            "id": 111,
            "title": "Senior AI Engineer",
            "location": {"name": "Remote - US"},
            "content": "<p>Build LLM agents.</p>",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/111",
            "updated_at": "2026-09-10T00:00:00Z",
            "departments": [{"name": "Engineering"}],
            "offices": [{"name": "Remote"}],
        },
        {
            # Malformed: missing "id" — must be skipped, not crash the batch.
            "title": "Broken Posting",
        },
    ]
}

LEVER_FIXTURE = [
    {
        "id": "abc123",
        "text": "ML Platform Engineer",
        "categories": {"location": "Remote", "commitment": "Full-time", "team": "ML"},
        "descriptionPlain": "Own our model-serving platform.",
        "hostedUrl": "https://jobs.lever.co/acme/abc123",
        "createdAt": 1757462400000,
    }
]


def _mock_response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_greenhouse_source_skips_malformed_postings():
    with patch("jobai.engine.sources.greenhouse.requests.get", return_value=_mock_response(GREENHOUSE_FIXTURE)):
        jobs = GreenhouseSource("Acme", "acme").fetch_jobs()
    assert len(jobs) == 1
    assert jobs[0].title == "Senior AI Engineer"
    assert jobs[0].source == "greenhouse"
    assert jobs[0].external_job_id == "111"


def test_lever_source_maps_fields():
    with patch("jobai.engine.sources.lever.requests.get", return_value=_mock_response(LEVER_FIXTURE)):
        jobs = LeverSource("Acme", "acme").fetch_jobs()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "lever"
    assert job.title == "ML Platform Engineer"
    assert job.location == "Remote"
    assert job.metadata["commitment"] == "Full-time"
