from unittest.mock import MagicMock, patch

from src.capabilities import analyse_job, get_priority_jobs
from src.jobs.schemas import JobClassification, JobMatch, NormalizedJob

FAKE_JOB = NormalizedJob(
    external_job_id="111",
    source="greenhouse",
    source_company_identifier="acme",
    company_name="Acme",
    title="Senior AI Engineer",
    location="Remote",
    workplace_type="Remote",
    description="Build production LLM agents and RAG systems.",
    job_url="https://boards.greenhouse.io/acme/jobs/111",
    job_fingerprint="greenhouse:111",
    description_hash="deadbeef",
)


def test_analyse_job_writes_match_back_to_notion():
    fake_page = {
        "notion_page_id": "page-abc",
        "Company": "Acme",
    }
    fake_classification = JobClassification(
        role_family="RF01",
        seniority="Senior",
        relevant=True,
        hard_blocker=False,
        key_requirements=["LLM agents", "RAG"],
    )
    fake_match = JobMatch(
        fit_band="strong",
        priority="P1",
        matched_achievements=[{"id": "A01", "strength": "strong", "supports": ["production AI"]}],
        strong_evidence=["production AI"],
        gaps=["PyTorch depth"],
        reason="Strong overlap with production AI ownership.",
        recommended_action="review",
    )

    with (
        patch("src.capabilities.NotionClient") as MockNotion,
        patch("src.capabilities.refetch_job", return_value=FAKE_JOB),
        patch("src.capabilities.classify_job", return_value=fake_classification),
        patch("src.capabilities.retrieve_achievements", return_value=[]),
        patch("src.capabilities.analyse_match", return_value=fake_match),
    ):
        mock_notion = MockNotion.return_value
        mock_notion.get_plain_by_fingerprint.return_value = fake_page

        result = analyse_job("greenhouse:111")

        assert result.fit_band == "strong"
        mock_notion.update_job_page.assert_called_once()
        page_id, properties = mock_notion.update_job_page.call_args[0]
        assert page_id == "page-abc"
        assert properties["Role Family"] == "RF01 - Senior/Lead AI Engineer"
        assert properties["Status"] is None  # "review" leaves Status untouched
        assert properties["Fit Band"] == "Strong"


def test_analyse_job_raises_when_job_not_in_notion():
    with patch("src.capabilities.NotionClient") as MockNotion:
        MockNotion.return_value.get_plain_by_fingerprint.return_value = None
        try:
            analyse_job("greenhouse:999")
            assert False, "expected ValueError"
        except ValueError:
            pass


def test_get_priority_jobs_delegates_to_notion_client():
    with patch("src.capabilities.NotionClient") as MockNotion:
        MockNotion.return_value.query_priority_jobs.return_value = [{"Opportunity": "AI Engineer — Acme"}]
        result = get_priority_jobs(limit=5)
        MockNotion.return_value.query_priority_jobs.assert_called_once_with(limit=5)
        assert result == [{"Opportunity": "AI Engineer — Acme"}]
