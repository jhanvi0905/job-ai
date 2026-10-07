"""Structured run logging (PRD §36). Plain stdlib logging + a per-run summary
counter — no external observability service for the MVP."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@dataclass
class RunSummary:
    """Accumulates the PRD §36 daily-operational-summary counters."""

    run_id: str | None = None
    fetched: int = 0
    duplicates: int = 0  # already in Notion (same id) or repeated within the run
    content_duplicates: int = 0  # same company+title already known (other source / re-post)
    previously_rejected: int = 0  # AI already rejected this exact JD — no new LLM call
    in_progress_skipped: int = 0  # page exists and you've moved it past Discovered
    stale_or_filtered: int = 0
    new_candidates: int = 0  # survived Stage 0 + dedup, sent to the AI
    classified: int = 0
    ai_rejected: int = 0  # Stage 1: wrong role type / fit too low
    deeply_analysed: int = 0
    match_rejected: int = 0  # Stage 3: fit below threshold
    written_to_notion: int = 0
    source_errors: list[str] = field(default_factory=list)
    ai_errors: list[str] = field(default_factory=list)
    estimated_cost_usd: float = 0.0
    rejections: list[str] = field(default_factory=list)  # 'title @ company: why', for inspection
    approvals: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        return (
            f"{self.fetched} jobs fetched\n"
            f"{self.stale_or_filtered} filtered out (Stage 0: location/years/seniority/title)\n"
            f"{self.duplicates} exact duplicates skipped\n"
            f"{self.content_duplicates} same-role duplicates skipped (other source / re-post)\n"
            f"{self.previously_rejected} previously AI-rejected, unchanged (0 tokens)\n"
            f"{self.in_progress_skipped} skipped (you're already working them)\n"
            f"{self.new_candidates} new candidates sent to AI\n"
            f"{self.classified} triaged (Stage 1) -> {self.ai_rejected} rejected\n"
            f"{self.deeply_analysed} deeply matched (Stage 3) -> {self.match_rejected} rejected\n"
            f"{self.written_to_notion} written/updated in Notion\n"
            f"{len(self.source_errors)} source/Notion errors\n"
            f"{len(self.ai_errors)} AI errors (retried next run)\n"
            f"estimated AI cost: ${self.estimated_cost_usd:.4f}"
        )
