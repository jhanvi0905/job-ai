from jobai.engine.jobs.normalize import infer_workplace_type, normalize_job, strip_html
from jobai.engine.jobs.schemas import RawJob


def test_strip_html_removes_tags_and_collapses_whitespace():
    html = "<p>Hello   <b>world</b></p>\n<div>!</div>"
    assert strip_html(html) == "Hello world !"


def test_strip_html_handles_none():
    assert strip_html(None) == ""


def test_infer_workplace_type_remote():
    assert infer_workplace_type("Remote - US") == "Remote"


def test_infer_workplace_type_hybrid():
    assert infer_workplace_type("Hybrid (SF)") == "Hybrid"


def test_infer_workplace_type_onsite():
    assert infer_workplace_type("San Francisco, CA") == "On-site"


def test_infer_workplace_type_unknown_for_empty():
    assert infer_workplace_type(None) == "Unknown"
    assert infer_workplace_type("") == "Unknown"


def test_normalize_job_never_fabricates_missing_fields():
    raw = RawJob(
        source="greenhouse",
        source_company_identifier="acme",
        external_job_id="1",
        title="AI Engineer",
        company_name="Acme",
        location=None,
        description_html=None,
        absolute_url="https://acme.example/jobs/1",
        updated_at=None,
    )
    job = normalize_job(raw)
    assert job.location is None
    assert job.description == ""
    assert job.posted_at is None
    assert job.workplace_type == "Unknown"
    assert job.job_fingerprint == "greenhouse:1"
    assert job.description_hash is not None


def test_normalize_job_computes_fingerprint_and_hash():
    raw = RawJob(
        source="greenhouse",
        source_company_identifier="acme",
        external_job_id="42",
        title="Senior AI Engineer",
        company_name="Acme",
        location="Remote",
        description_html="<p>Build agents.</p>",
        absolute_url="https://acme.example/jobs/42",
        updated_at="2026-09-10T00:00:00Z",
    )
    job = normalize_job(raw)
    assert job.job_fingerprint == "greenhouse:42"
    assert job.workplace_type == "Remote"
    assert job.description == "Build agents."
    assert job.posted_at is not None
