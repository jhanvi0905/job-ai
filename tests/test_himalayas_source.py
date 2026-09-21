from unittest.mock import MagicMock, patch

from src.jobs.normalize import normalize_job
from src.sources.himalayas import HimalayasSource

HIMALAYAS_FIXTURE = {
    "totalCount": 2,
    "jobs": [
        {
            "title": "AI Platform Engineer",
            "companyName": "Granicus",
            "companySlug": "granicus",
            "employmentType": "Full-time",
            "locationRestrictions": ["India", "United States", "Canada"],
            "description": "<p>Build our AI platform.</p>",
            "applicationLink": "https://himalayas.app/companies/granicus/jobs/ai-platform-engineer",
            "guid": "https://himalayas.app/companies/granicus/jobs/ai-platform-engineer",
            "pubDate": 1790000000,
        },
        {
            "title": "Machine Learning Engineer",
            "companyName": "micro1",
            "companySlug": "micro1",
            "employmentType": "Contractor",
            "locationRestrictions": [],
            "description": "<p>Worldwide remote ML role.</p>",
            "applicationLink": "https://himalayas.app/companies/micro1/jobs/ml-engineer",
            "guid": "https://himalayas.app/companies/micro1/jobs/ml-engineer",
            "pubDate": 1790000001,
        },
    ],
}


def _mock_response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_himalayas_source_uses_each_jobs_own_company_not_the_query_label():
    with patch("src.sources.himalayas.requests.get", return_value=_mock_response(HIMALAYAS_FIXTURE)):
        jobs = HimalayasSource("Himalayas: India · AI Engineer", "country=IN&q=AI+engineer").fetch_jobs()
    assert len(jobs) == 2
    assert jobs[0].company_name == "Granicus"
    assert jobs[1].company_name == "micro1"


def test_himalayas_restricted_country_list_becomes_location_text():
    with patch("src.sources.himalayas.requests.get", return_value=_mock_response(HIMALAYAS_FIXTURE)):
        jobs = HimalayasSource("q", "country=IN").fetch_jobs()
    restricted, worldwide = jobs
    assert "India" in restricted.location
    normalized = normalize_job(restricted)
    assert normalized.workplace_type == "Remote"


def test_himalayas_empty_restrictions_becomes_worldwide():
    with patch("src.sources.himalayas.requests.get", return_value=_mock_response(HIMALAYAS_FIXTURE)):
        jobs = HimalayasSource("q", "worldwide=true").fetch_jobs()
    _, worldwide_job = jobs
    assert worldwide_job.location == "Worldwide"
