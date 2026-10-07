"""Loads the config/*.yaml files. Single place so nothing scatters constants
across the codebase (PRD §27)."""
from __future__ import annotations

from functools import cache

import yaml

from jobai.core.paths import CONFIG_DIR, local_or_example


@cache
def load_yaml(name: str) -> dict:
    path = local_or_example(CONFIG_DIR / name)
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_sources() -> list[dict]:
    return load_yaml("sources.yaml")["companies"]


def load_roles() -> dict:
    return load_yaml("roles.yaml")


def load_career_rules() -> dict:
    return load_yaml("career_rules.yaml")


def load_models() -> dict:
    return load_yaml("models.yaml")


def load_candidate_profile() -> dict:
    return load_yaml("candidate_profile.yaml")
