from src.ai.matcher import score_match


def req(text, importance, evidence, ids=()):
    return {"req": text, "importance": importance, "evidence": evidence, "achievement_ids": list(ids)}


def test_strong_needs_most_core_direct_and_no_core_gap():
    m = score_match({"requirements": [
        req("LLM systems", "core", "direct", ["A05"]),
        req("RAG", "core", "direct", ["A01"]),
        req("Python", "core", "direct", ["A01"]),
        req("Kubernetes", "secondary", "none"),
    ], "reason": "ok"})
    assert m.fit_band == "strong" and m.priority == "P1"
    assert m.gaps == ["Kubernetes"]  # a secondary gap doesn't stop 'strong', but is reported


def test_one_missing_core_requirement_caps_at_plausible():
    m = score_match({"requirements": [
        req("LLM systems", "core", "direct", ["A05"]),
        req("RAG", "core", "direct", ["A01"]),
        req("Model pre-training", "core", "none"),
    ], "reason": "x"})
    assert m.fit_band == "plausible" and m.priority == "P2"
    assert m.gaps == ["Model pre-training"]


def test_mostly_unsupported_core_is_weak_and_rejected():
    m = score_match({"requirements": [
        req("A", "core", "none"), req("B", "core", "none"), req("C", "core", "adjacent", ["A02"]),
    ], "reason": "x"})
    assert m.fit_band == "weak" and m.recommended_action == "reject"


def test_adjacent_evidence_counts_for_plausible():
    m = score_match({"requirements": [
        req("Azure Databricks", "core", "adjacent", ["A08"]),
        req("Spark", "core", "adjacent", ["A08"]),
        req("Python", "core", "direct", ["A10"]),
    ], "reason": "x"})
    assert m.fit_band == "plausible"


def test_blocker_overrides_everything():
    m = score_match({"blocker": True, "requirements": [req("x", "core", "direct", ["A01"])], "reason": "r"})
    assert m.fit_band == "blocked" and m.recommended_action == "reject"


def test_no_requirements_extracted_is_weak_not_a_crash():
    assert score_match({"requirements": [], "reason": ""}).fit_band == "weak"


def test_matched_achievements_prefer_strongest_evidence():
    m = score_match({"requirements": [
        req("a", "core", "adjacent", ["A08"]), req("b", "core", "direct", ["A08"]),
    ], "reason": "r"})
    assert [(a.id, a.strength) for a in m.matched_achievements] == [("A08", "strong")]
