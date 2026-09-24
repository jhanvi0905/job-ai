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
