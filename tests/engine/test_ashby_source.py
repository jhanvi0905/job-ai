from unittest.mock import MagicMock, patch

from jobai.engine.jobs.normalize import normalize_job
from jobai.engine.sources.ashby import AshbySource

ASHBY_FIXTURE = {
    "jobs": [
        {
            "id": "abc-123",
            "title": "Senior AI Engineer",
            "location": "Remote",
            "workplaceType": "Remote",
            "isRemote": True,
            "descriptionHtml": "<p>Build agentic systems.</p>",
            "jobUrl": "https://jobs.ashbyhq.com/acme/abc-123",
            "publishedAt": "2026-09-10T00:00:00.000+00:00",
            "address": {"postalAddress": {"addressCountry": "United States"}},
        },
        {
            "id": "def-456",
            "title": "Platform Engineer",
            "location": "Bengaluru",
            "workplaceType": "OnSite",
            "isRemote": False,
            "descriptionHtml": "<p>Own our India platform team.</p>",
            "jobUrl": "https://jobs.ashbyhq.com/acme/def-456",
            "publishedAt": "2026-09-12T00:00:00.000+00:00",
            "address": {"postalAddress": {"addressCountry": "India"}},
        },
    ]
}


def _mock_response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_ashby_source_maps_structured_fields():
    with patch("jobai.engine.sources.ashby.requests.get", return_value=_mock_response(ASHBY_FIXTURE)):
        jobs = AshbySource("Acme", "acme").fetch_jobs()
    assert len(jobs) == 2
    assert jobs[0].metadata["workplace_type"] == "Remote"
    assert jobs[1].metadata["location_country"] == "India"


def test_normalize_uses_ashby_structured_workplace_type_and_country():
    with patch("jobai.engine.sources.ashby.requests.get", return_value=_mock_response(ASHBY_FIXTURE)):
        raw_jobs = AshbySource("Acme", "acme").fetch_jobs()

    onsite_india = normalize_job(raw_jobs[1])
    assert onsite_india.workplace_type == "On-site"
    assert onsite_india.location_country == "India"

    remote_us = normalize_job(raw_jobs[0])
    assert remote_us.workplace_type == "Remote"
    assert remote_us.location_country == "United States"
