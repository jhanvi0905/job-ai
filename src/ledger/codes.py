"""Closed vocabularies for the ledger — the queryable dimensions.

Free text is for humans; these enums are for GROUP BY. Keeping them closed (and
enforced by CHECK constraints in the schema) is what makes "which layer fails?"
a one-line query, and makes an unrecognised value a loud error rather than a
silently growing 'other' bucket.

Grouped by the layer that failed, mirroring the pipeline: call -> context ->
model output -> policy. Later phases add item-level dispositions and more codes
through a schema migration, not by editing rows in place.
"""

# Outcome of ONE HTTP attempt to the model provider.
CALL_OK = "ok"
CALL_OUTCOMES = frozenset(
    {
        "ok",
        # transport / provider layer (retryable)
        "http_429",
        "http_5xx",
        "timeout",
        "connection_error",
        # transport / provider layer (not retryable)
        "http_4xx",
        # model output layer
        "invalid_json",  # response body/content was not parseable JSON
        "truncated",  # finish_reason == "length": output cut off by max_tokens
        "schema_invalid",  # parsed, but failed the caller's schema validation
        # our own guardrails (no HTTP call was made)
        "budget_exceeded",
        "circuit_open",
    }
)

RETRYABLE_OUTCOMES = frozenset({"http_429", "http_5xx", "timeout", "connection_error", "invalid_json"})

RUN_STATUSES = frozenset({"running", "ok", "degraded", "failed"})


def sql_in(values: frozenset[str]) -> str:
    """Render a frozenset as a SQL IN-list literal for a CHECK constraint.
    Values are our own constants, never user input."""
    return ", ".join(f"'{v}'" for v in sorted(values))


# ---------------------------------------------------------------------------
# Item-level vocabulary (Phase 2). Every item that enters a node must leave it
# with exactly ONE terminal event, so a missing row is a bug we can detect.
# ---------------------------------------------------------------------------
NODES = frozenset({"fetch", "stage0", "dedupe", "triage", "match", "write"})

# passed   -> continues downstream
# rejected -> a verdict: the item is finished (and remembered) as not wanted
# skipped  -> filtered/deduped by deterministic rules, no verdict involved
# deferred -> NOT judged; will be retried next run (budget, breaker, cap)
# errored  -> attempted and failed; will be retried next run
DISPOSITIONS = frozenset({"passed", "rejected", "skipped", "deferred", "errored"})

_STAGE0_FILTERS = frozenset({
    "stale", "location_restricted", "location_unknown", "workplace_type", "employment_type",
    "junior_title", "too_senior_title", "years_too_high", "junior_ask", "hard_exclusion",
    "no_signal", "analyst_title", "generic_title", "stage0_other",
})
_LLM_FAILURES = frozenset({"llm_budget", "llm_circuit", "llm_schema", "llm_error"})

# Which reason codes are legal at which node. A mis-coded event is rejected
# at write time instead of quietly polluting the analysis.
NODE_REASONS: dict[str, frozenset[str]] = {
    "fetch": frozenset({"normalized", "normalize_failed"}),
    "stage0": _STAGE0_FILTERS | {"passed_stage0", "duplicate_in_run"},
    "dedupe": frozenset({"passed_dedupe", "duplicate_id", "duplicate_role", "in_progress", "previously_rejected"}),
    "triage": _LLM_FAILURES | {"approved_triage", "rejected_role_type", "rejected_fit_low", "rejected_blocker"},
    "match": _LLM_FAILURES | {"approved_match", "rejected_weak", "rejected_blocked", "rejected_action", "cap_overflow"},
    "write": frozenset({"written_new", "written_update", "notion_error"}),
}
REASON_CODES = frozenset().union(*NODE_REASONS.values())
