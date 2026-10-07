"""Graph state for the LangGraph orchestrator layer.

This is new state private to the orchestrator — it does not replace or wrap
anything in jobai.assistant.capabilities, it just records what the orchestrator decided
to call and what happened.
"""
from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import add_messages


class CapabilityCall(TypedDict):
    name: Literal["discover_jobs", "analyse_job", "get_priority_jobs", "sync_inbox"]
    args: dict
    result_summary: str
    ledger_run_id: str | None
    status: Literal["ok", "failed", "deferred"]


class OrchestratorState(TypedDict):
    messages: Annotated[list, add_messages]
    calls: Annotated[list[CapabilityCall], operator.add]
    pending_confirmation: CapabilityCall | None
    session_summary: str | None
