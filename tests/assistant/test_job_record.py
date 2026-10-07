from jobai.assistant.integrations.job_record import base_properties, evaluation_properties, location_display
from jobai.engine.jobs.schemas import JobClassification, JobMatch, NormalizedJob


def job(**o) -> NormalizedJob:
    d = dict(
        external_job_id="1", source="himalayas", source_company_identifier="a", company_name="Acme",
        title="ML Engineer", location="Worldwide", workplace_type="Remote", description="x",
        job_url="https://x", job_fingerprint="himalayas:1", description_hash="h",
    )
    d.update(o)
    return NormalizedJob(**d)


def test_himalayas_is_not_labelled_company_careers():
    assert base_properties(job(), True)["Source Channel"] == "Other"
    assert base_properties(job(source="greenhouse"), True)["Source Channel"] == "Company Careers"


def test_country_lists_are_shortened_for_readability():
    long = "Armenia, Australia, Canada, India, New Zealand, United Kingdom, United States"
    assert location_display(job(location=long)) == "India + 6 more (remote)"
    assert location_display(job(location="India")) == "India (remote)"
    assert location_display(job(location="Worldwide")) == "Worldwide (remote)"


def test_updates_never_reset_status_or_found_date():
    update = base_properties(job(), is_new=False)
    assert "Status" not in update and "Found Date" not in update
    create = base_properties(job(), is_new=True)
    assert create["Status"] == "Discovered" and "Found Date" in create


def test_seniority_uses_fixed_vocabulary_not_model_free_text():
    c = JobClassification(relevant=True, seniority="staff_plus", role_family="RF01")
    assert evaluation_properties(c, None)["Seniority"] == "Staff+"
    junk = JobClassification(relevant=True, seniority="L1")
    assert evaluation_properties(junk, None)["Seniority"] is None  # unknown -> blank, not junk


def test_years_shortfall_is_surfaced_as_a_gap():
    c = JobClassification(relevant=True, min_years_required=5)
    m = JobMatch(fit_band="plausible", priority="P2", reason="r", gaps=["Kafka"])
    props = evaluation_properties(c, m)
    assert props["Gaps"].startswith("Asks 5+ yrs experience (you have ~3)")
    assert "Kafka" in props["Gaps"]
    assert props["Priority"] == "P2" and props["Fit Band"] == "Plausible"


def test_no_years_gap_when_role_is_within_reach():
    c = JobClassification(relevant=True, min_years_required=2)
    m = JobMatch(fit_band="strong", priority="P1", reason="r")
    assert evaluation_properties(c, m)["Gaps"] is None
