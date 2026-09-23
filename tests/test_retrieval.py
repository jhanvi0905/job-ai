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


def test_data_platform_evidence_is_now_retrievable_for_data_roles():
    results = retrieve_achievements("RF03", ["Kafka streaming pipelines", "BigQuery", "dbt"])
    assert results and results[0].id == "A08"
    assert "RisingWave" in results[0].summary


def test_matcher_never_receives_an_empty_evidence_set_for_a_known_family():
    results = retrieve_achievements("RF02", ["quantum widgets"])
    assert len(results) >= 3 and all(r.summary for r in results)


def test_index_is_synced_to_bank_v8():
    from src.achievements.loader import load_achievement_index

    idx = {a["id"]: a for a in load_achievement_index()}
    assert {"A11", "A12", "A13"} <= idx.keys()
    # v8 A04: gate agent is user-confirmed LangChain, NOT Google ADK
    assert "LangChain" in idx["A04"]["skills"] and "Google ADK" not in idx["A04"]["skills"]


def test_finetuning_and_databricks_evidence_are_retrievable():
    assert "A13" in [r.id for r in retrieve_achievements("RF02", ["LLM fine-tuning with QLoRA"])]
    assert "A11" in [r.id for r in retrieve_achievements("RF03", ["Databricks", "Delta Lake"])]
