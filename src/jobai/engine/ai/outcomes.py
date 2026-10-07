"""How a failed or blocked LLM call is recorded. Shared by every pipeline so a
budget stop is never mistaken for a verdict anywhere."""
from __future__ import annotations

from jobai.engine.ai.classifier import FIT_RANK
from jobai.engine.ai.provider import BudgetExceeded, CircuitOpen, SchemaError

# Stage 3 can also say "blocked" (a hard requirement the candidate lacks).
MATCH_FIT_RANK = {**FIT_RANK, "blocked": 0}


def llm_failure(exc: Exception) -> tuple[str, str]:
    """(disposition, reason code). Budget/breaker stops are DEFERRALS (never
    judged, retried next run); real failures are ERRORS. Neither is a verdict."""
    if isinstance(exc, BudgetExceeded):
        return "deferred", "llm_budget"
    if isinstance(exc, CircuitOpen):
        return "deferred", "llm_circuit"
    if isinstance(exc, SchemaError):
        return "errored", "llm_schema"
    return "errored", "llm_error"
