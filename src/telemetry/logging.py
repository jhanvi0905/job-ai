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

    fetched: int = 0
    duplicates: int = 0
    stale_or_filtered: int = 0
    new_candidates: int = 0
    classified: int = 0
    deeply_analysed: int = 0
    written_to_notion: int = 0
    source_errors: list[str] = field(default_factory=list)
    ai_errors: list[str] = field(default_factory=list)
    estimated_cost_usd: float = 0.0

    def as_text(self) -> str:
        return (
            f"{self.fetched} jobs fetched\n"
            f"{self.duplicates} duplicates/unchanged skipped\n"
            f"{self.stale_or_filtered} filtered out (Stage 0)\n"
            f"{self.new_candidates} new candidates survived Stage 0\n"
            f"{self.classified} triaged (Stage 1)\n"
            f"{self.deeply_analysed} deeply analysed (Stage 3)\n"
            f"{self.written_to_notion} written/updated in Notion\n"
            f"{len(self.source_errors)} source errors\n"
            f"{len(self.ai_errors)} AI errors\n"
            f"estimated AI cost: ${self.estimated_cost_usd:.4f}"
        )
