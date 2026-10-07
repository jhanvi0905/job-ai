"""Graph structure and state handling — no live LLM, no live network.
decide_next_action is injected directly (build_orchestrator_graph takes it
as a parameter), so routing logic itself isn't under test here.
"""
from unittest.mock import patch

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from jobai.assistant.orchestrator.graph import build_orchestrator_graph, decide_next_action
from jobai.engine.jobs.schemas import JobMatch


def _init_state(text: str) -> dict:
    return {"messages": [HumanMessage(text)], "calls": [], "pending_confirmation": None, "session_summary": None}


def _decide_analyse_job(state, preferences):
    return {
        "name": "analyse_job",
        "args": {"job_fingerprint": "greenhouse:1"},
        "result_summary": "",
        "ledger_run_id": None,
        "status": "deferred",
    }


def _decide_get_priority_jobs(state, preferences):
    return {
        "name": "get_priority_jobs",
        "args": {"limit": 5},
        "result_summary": "",
        "ledger_run_id": None,
        "status": "deferred",
    }


def _decide_nothing(state, preferences):
    return None


def test_write_capability_pauses_for_confirmation():
    graph = build_orchestrator_graph(decide_next_action_fn=_decide_analyse_job)
    config = {"configurable": {"thread_id": "t-confirm"}}

    result = graph.invoke(_init_state("please analyse this job"), config)

    assert result["__interrupt__"], "expected the graph to interrupt before a write capability"
    assert result["pending_confirmation"] == {
        "name": "analyse_job",
        "args": {"job_fingerprint": "greenhouse:1"},
        "result_summary": "",
        "ledger_run_id": None,
        "status": "deferred",
    }
    assert result["calls"] == []
    assert graph.get_state(config).next == ("confirm",)


def test_approving_confirmation_resumes_and_appends_call():
    graph = build_orchestrator_graph(decide_next_action_fn=_decide_analyse_job)
    config = {"configurable": {"thread_id": "t-approve"}}
    graph.invoke(_init_state("please analyse this job"), config)

    match = JobMatch(fit_band="strong", priority="P1", reason="x", run_id="run-9")
    with patch("jobai.assistant.orchestrator.tools.capabilities.analyse_job", return_value=match):
        result = graph.invoke(Command(resume=True), config)

    assert result["calls"] == [
        {
            "name": "analyse_job",
            "args": {"job_fingerprint": "greenhouse:1"},
            "result_summary": "strong fit, priority P1",
            "ledger_run_id": "run-9",
            "status": "ok",
        }
    ]
    assert result["pending_confirmation"] is None
    assert graph.get_state(config).next == ()


def test_rejecting_confirmation_records_a_failed_call_without_executing():
    graph = build_orchestrator_graph(decide_next_action_fn=_decide_analyse_job)
    config = {"configurable": {"thread_id": "t-reject"}}
    graph.invoke(_init_state("please analyse this job"), config)

    with patch("jobai.assistant.orchestrator.tools.capabilities.analyse_job") as mock_analyse:
        result = graph.invoke(Command(resume=False), config)

    mock_analyse.assert_not_called()
    assert result["calls"] == [
        {
            "name": "analyse_job",
            "args": {"job_fingerprint": "greenhouse:1"},
            "result_summary": "cancelled: not approved",
            "ledger_run_id": None,
            "status": "failed",
        }
    ]
    assert result["pending_confirmation"] is None


def test_read_only_capability_runs_straight_through_without_interrupt():
    graph = build_orchestrator_graph(decide_next_action_fn=_decide_get_priority_jobs)
    config = {"configurable": {"thread_id": "t-readonly"}}

    with patch("jobai.assistant.orchestrator.tools.capabilities.get_priority_jobs", return_value=[{"Opportunity": "X"}]):
        result = graph.invoke(_init_state("show me the priority queue"), config)

    assert "__interrupt__" not in result or not result["__interrupt__"]
    assert result["calls"] == [
        {
            "name": "get_priority_jobs",
            "args": {"limit": 5},
            "result_summary": "1 jobs in review queue",
            "ledger_run_id": None,
            "status": "ok",
        }
    ]
    assert graph.get_state(config).next == ()


def test_no_decision_ends_the_run_with_no_calls():
    graph = build_orchestrator_graph(decide_next_action_fn=_decide_nothing)
    config = {"configurable": {"thread_id": "t-noop"}}

    result = graph.invoke(_init_state("hello there"), config)

    assert result["calls"] == []
    assert result["pending_confirmation"] is None
    assert graph.get_state(config).next == ()


def test_sync_inbox_is_gated_because_it_writes_notion_status():
    def decide(state, preferences):
        return {"name": "sync_inbox", "args": {}, "result_summary": "", "ledger_run_id": None, "status": "deferred"}

    graph = build_orchestrator_graph(decide_next_action_fn=decide)
    config = {"configurable": {"thread_id": "t-inbox"}}

    result = graph.invoke(_init_state("check my inbox"), config)

    assert result["__interrupt__"]
    assert graph.get_state(config).next == ("confirm",)


def test_route_falls_back_to_empty_preferences_when_file_missing(tmp_path):
    seen = {}

    def decide(state, preferences):
        seen["preferences"] = preferences
        return None

    graph = build_orchestrator_graph(
        decide_next_action_fn=decide, preferences_path=tmp_path / "does-not-exist.json"
    )
    config = {"configurable": {"thread_id": "t-missing-prefs"}}

    graph.invoke(_init_state("hello"), config)

    assert seen["preferences"] == {"rejection_patterns": [], "reject_reasons": {}, "interaction_prefs": {}}


def test_default_decide_next_action_is_rule_based_placeholder():
    state = {"messages": [HumanMessage("go discover new jobs")], "calls": [], "pending_confirmation": None, "session_summary": None}
    decided = decide_next_action(state, {"rejection_patterns": [], "reject_reasons": {}, "interaction_prefs": {}})
    assert decided["name"] == "discover_jobs"
    assert decided["status"] == "deferred"

    state = {"messages": [HumanMessage("sync my email inbox")], "calls": [], "pending_confirmation": None, "session_summary": None}
    decided = decide_next_action(state, {})
    assert decided["name"] == "sync_inbox"

    state = {"messages": [HumanMessage("what's the weather")], "calls": [], "pending_confirmation": None, "session_summary": None}
    assert decide_next_action(state, {}) is None
