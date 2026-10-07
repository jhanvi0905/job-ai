"""Repository-relative locations of config, prompts and local data.

One place resolves them so modules never count `parent.parent` hops. Override the
root with JOBAI_HOME when the code runs from an installed wheel instead of a checkout.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(os.environ.get("JOBAI_HOME") or Path(__file__).resolve().parents[3])
CONFIG_DIR = REPO_ROOT / "config"
PROMPTS_DIR = REPO_ROOT / "prompts"
DATA_DIR = REPO_ROOT / "data"


def local_or_example(path: Path) -> Path:
    """Personal files (profile, achievement index) are gitignored; a fresh checkout
    falls back to the committed `*.example.*` sibling so everything still runs."""
    if path.exists():
        return path
    return path.with_name(f"{path.stem}.example{path.suffix}")
