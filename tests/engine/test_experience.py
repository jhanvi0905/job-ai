from jobai.engine.jobs.experience import extract_required_years


def test_plus_years_of_experience():
    r = extract_required_years("You have 5+ years of experience building ML systems.")
    assert r and r.min_years == 5


def test_range_years():
    r = extract_required_years("Requires 3-5 years of professional experience in data engineering.")
    assert r and (r.min_years, r.max_years) == (3, 5)


def test_takes_overall_requirement_over_per_skill_asks():
    text = "8+ years of software engineering experience. 3+ years of experience with Python."
    assert extract_required_years(text).min_years == 8


def test_ignores_company_history_without_experience_context():
    assert extract_required_years("Founded 12 years ago, we serve millions of users.") is None


def test_ignores_preferred_years():
    assert extract_required_years("10+ years of experience is a plus but not required.") is None


def test_no_requirement_returns_none():
    assert extract_required_years("Join our team and build cool things.") is None


def test_at_least_phrasing():
    r = extract_required_years("At least 7 years of relevant experience is required.")
    assert r and r.min_years == 7
