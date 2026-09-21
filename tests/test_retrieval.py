from src.achievements.retrieval import retrieve_achievements


def test_retrieval_favors_role_family_and_skill_overlap():
    results = retrieve_achievements(
        role_family="RF01",
        key_requirements=["production AI", "multi-agent orchestration", "BigQuery"],
    )
    ids = [r.id for r in results]
    # A01/A02/A03 all touch production AI + BigQuery + RF01 — should surface near the top.
    assert "A01" in ids or "A02" in ids or "A03" in ids
    assert results[0].score > 0


def test_retrieval_returns_empty_when_nothing_matches():
    results = retrieve_achievements(role_family=None, key_requirements=["quantum chemistry simulation"])
    assert results == []


def test_retrieval_respects_top_k():
    results = retrieve_achievements(
        role_family="RF01",
        key_requirements=["production AI", "architecture", "0-to-1"],
        top_k=2,
    )
    assert len(results) <= 2
