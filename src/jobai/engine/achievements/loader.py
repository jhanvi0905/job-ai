"""Loads the compact achievement retrieval index (data/achievements_index.yaml).
Never touches the canonical docx — that document is read by a human once
per new frozen achievement and this index is updated by hand (PRD §7-8)."""
from __future__ import annotations

from functools import cache

import yaml

from jobai.core.paths import DATA_DIR, local_or_example

INDEX_PATH = DATA_DIR / "achievements_index.yaml"


@cache
def load_achievement_index() -> list[dict]:
    with local_or_example(INDEX_PATH).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)["achievements"]
