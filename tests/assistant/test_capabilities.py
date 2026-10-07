from unittest.mock import patch

from jobai.assistant.capabilities import analyse_job, get_priority_jobs, sync_inbox
from jobai.engine.jobs.schemas import JobClassification, JobMatch, NormalizedJob

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
        patch("jobai.assistant.capabilities.NotionClient") as MockNotion,
        patch("jobai.assistant.capabilities.refetch_job", return_value=FAKE_JOB),
        patch("jobai.assistant.capabilities.classify_job", return_value=fake_classification),
        patch("jobai.assistant.capabilities.retrieve_achievements", return_value=[]),
        patch("jobai.assistant.capabilities.analyse_match", return_value=fake_match),
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
    with patch("jobai.assistant.capabilities.NotionClient") as MockNotion:
        MockNotion.return_value.get_plain_by_fingerprint.return_value = None
        try:
            analyse_job("greenhouse:999")
            raise AssertionError("expected ValueError")
        except ValueError:
            pass


def test_get_priority_jobs_delegates_to_notion_client():
    with patch("jobai.assistant.capabilities.NotionClient") as MockNotion:
        MockNotion.return_value.query_priority_jobs.return_value = [{"Opportunity": "AI Engineer — Acme"}]
        result = get_priority_jobs(limit=5)
        MockNotion.return_value.query_priority_jobs.assert_called_once_with(limit=5)
        assert result == [{"Opportunity": "AI Engineer — Acme"}]


def test_sync_inbox_delegates_to_inbox_run():
    fake_summary = object()
    with patch("jobai.assistant.capabilities._run_inbox_sync", return_value=fake_summary) as mock_run:
        result = sync_inbox(dry_run=True, lookback_days=7)
        mock_run.assert_called_once_with(dry_run=True, lookback_days=7)
        assert result is fake_summary
