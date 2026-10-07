"""LangGraph orchestrator: route -> [confirm] -> execute.

route decides WHICH capability to call next (via decide_next_action, an
injectable placeholder — the real routing LLM call is a follow-up task, not
this one). confirm gates any write-capable capability behind a human
approval using LangGraph's interrupt() mechanism. execute runs the approved
(or non-write) capability through jobai.assistant.orchestrator.tools and appends the
result to state["calls"].
"""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from jobai.assistant.orchestrator import tools
from jobai.assistant.orchestrator.state import CapabilityCall, OrchestratorState

DEFAULT_PREFERENCES_PATH = "data/routing_preferences.json"
_EMPTY_PREFERENCES = {"rejection_patterns": [], "reject_reasons": {}, "interaction_prefs": {}}

# discover_jobs and analyse_job write to Notion directly; sync_inbox also
# updates job status on Notion pages for matched replies (see
# src/jobai/assistant/workflows/inbox.py). get_priority_jobs is read-only. Per the "model
# only judges, code decides" rule, none of these fire without a human
# confirming first.
_WRITE_CAPABILITIES = {"discover_jobs", "analyse_job", "sync_inbox"}

_DISPATCH: dict[str, Callable[..., CapabilityCall]] = {
    "discover_jobs": lambda **kw: tools.call_discover_jobs(),
    "analyse_job": lambda **kw: tools.call_analyse_job(**kw),
    "get_priority_jobs": lambda **kw: tools.call_get_priority_jobs(**kw),
    "sync_inbox": lambda **kw: tools.call_sync_inbox(**kw),
}


def _load_preferences(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        return dict(_EMPTY_PREFERENCES)
    return json.loads(p.read_text())


def decide_next_action(state: OrchestratorState, preferences: dict) -> CapabilityCall | None:
    """PLACEHOLDER routing decision — rule-based stand-in for the real LLM
    call (a follow-up task). Only decides WHICH capability and its args;
    never decides whether it's allowed to run without confirmation, that's
    the graph's job, not this function's."""
    messages = state.get("messages") or []
    if not messages:
        return None
    last = messages[-1]
    text = getattr(last, "content", last)
    text = str(text).lower()

    if "inbox" in text or "email" in text:
        return {"name": "sync_inbox", "args": {}, "result_summary": "", "ledger_run_id": None, "status": "deferred"}
    if "priority" in text or "queue" in text:
        return {
            "name": "get_priority_jobs",
            "args": {"limit": 15},
            "result_summary": "",
            "ledger_run_id": None,
            "status": "deferred",
        }
    if "analyse" in text or "analyze" in text:
        return None  # placeholder can't extract a job_fingerprint from free text yet
    if "job" in text:
        return {"name": "discover_jobs", "args": {}, "result_summary": "", "ledger_run_id": None, "status": "deferred"}
    return None


def build_orchestrator_graph(
    decide_next_action_fn: Callable[[OrchestratorState, dict], CapabilityCall | None] = decide_next_action,
    preferences_path: str | Path = DEFAULT_PREFERENCES_PATH,
):
    def route(state: OrchestratorState) -> dict:
        preferences = _load_preferences(preferences_path)
        decided = decide_next_action_fn(state, preferences)
        return {"pending_confirmation": decided}

    def route_edge(state: OrchestratorState) -> str:
        call = state["pending_confirmation"]
        if call is None:
            return END
        return "confirm" if call["name"] in _WRITE_CAPABILITIES else "execute"

    def confirm(state: OrchestratorState) -> dict:
        call = state["pending_confirmation"]
        approved = interrupt({"call": call, "question": f"Approve {call['name']}({call['args']})?"})
        if not approved:
            cancelled: CapabilityCall = {
                **call,
                "status": "failed",
                "result_summary": "cancelled: not approved",
            }
            return {"calls": [cancelled], "pending_confirmation": None}
        return {"pending_confirmation": call}

    def confirm_edge(state: OrchestratorState) -> str:
        return "execute" if state["pending_confirmation"] is not None else END

    def execute(state: OrchestratorState) -> dict:
        call = state["pending_confirmation"]
        result = _DISPATCH[call["name"]](**call["args"])
        return {"calls": [result], "pending_confirmation": None}

    graph = StateGraph(OrchestratorState)
    graph.add_node("route", route)
    graph.add_node("confirm", confirm)
    graph.add_node("execute", execute)

    graph.add_edge(START, "route")
    graph.add_conditional_edges("route", route_edge, {"confirm": "confirm", "execute": "execute", END: END})
    graph.add_conditional_edges("confirm", confirm_edge, {"execute": "execute", END: END})
    graph.add_edge("execute", END)

    return graph.compile(checkpointer=InMemorySaver())
