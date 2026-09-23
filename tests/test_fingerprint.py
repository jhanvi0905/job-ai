from src.jobs.fingerprint import compute_description_hash, compute_fingerprint


def test_fingerprint_prefers_source_and_external_id():
    fp = compute_fingerprint("greenhouse", "12345", "Acme", "AI Engineer", "Remote", "https://x")
    assert fp == "greenhouse:12345"


def test_fingerprint_stable_across_calls():
    args = ("greenhouse", "12345", "Acme", "AI Engineer", "Remote", "https://x")
    assert compute_fingerprint(*args) == compute_fingerprint(*args)


def test_fingerprint_falls_back_to_content_hash_when_id_missing():
    fp = compute_fingerprint("scrape", "", "Acme", "AI Engineer", "Remote", "https://x")
    assert fp.startswith("fallback:")


def test_fallback_fingerprint_ignores_whitespace_and_case():
    fp1 = compute_fingerprint("scrape", "", "Acme", "AI Engineer", "Remote", "https://x")
    fp2 = compute_fingerprint("scrape", "", "  ACME  ", "ai engineer", "remote", "https://x")
    assert fp1 == fp2


def test_description_hash_changes_with_content():
    h1 = compute_description_hash("We need a senior AI engineer.")
    h2 = compute_description_hash("We need a senior ML engineer.")
    assert h1 != h2


def test_description_hash_stable_for_same_content_different_whitespace():
    h1 = compute_description_hash("Hello   world")
    h2 = compute_description_hash("Hello world  ")
    assert h1 == h2


def test_content_key_matches_same_role_across_sources_and_noise():
    from src.jobs.fingerprint import content_key

    a = content_key("Project Management Institute, Inc.", "AI Engineer, Marketing")
    b = content_key("project management institute", "AI Engineer, Marketing (Remote)")
    assert a == b


def test_content_key_distinguishes_different_roles_and_companies():
    from src.jobs.fingerprint import content_key

    assert content_key("Acme", "Senior ML Engineer") != content_key("Acme", "Senior Data Engineer")
    assert content_key("Acme", "ML Engineer") != content_key("Globex", "ML Engineer")
    # parenthetical team names are real differences, not noise
    assert content_key("Databricks", "Senior Software Engineer (Backend)") != content_key(
        "Databricks", "Senior Software Engineer (Search)"
    )
