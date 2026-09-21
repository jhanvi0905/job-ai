"""Loads the compact achievement retrieval index (data/achievements_index.yaml).
Never touches the canonical docx — that document is read by a human once
per new frozen achievement and this index is updated by hand (PRD §7-8)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

INDEX_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "achievements_index.yaml"


@lru_cache(maxsize=None)
def load_achievement_index() -> list[dict]:
    with INDEX_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)["achievements"]
