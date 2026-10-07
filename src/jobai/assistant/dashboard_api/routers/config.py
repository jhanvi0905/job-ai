"""Read/preview/apply the config/*.yaml files that drive the pipeline.

CONFIG_DIR is a module-level global (not bound into closures) so tests can
monkeypatch `jobai.assistant.dashboard_api.routers.config.CONFIG_DIR` to a tmp_path full
of fixture files without touching the real config/ directory.
"""
from __future__ import annotations

import difflib

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from jobai.core.config import CONFIG_DIR, load_yaml

router = APIRouter()

ALLOWED_FILES = ["career_rules.yaml", "candidate_profile.yaml", "roles.yaml", "sources.yaml", "models.yaml"]


class PreviewRequest(BaseModel):
    content: str


class ApplyRequest(BaseModel):
    content: str
    confirm: bool = False


def _require_known(name: str) -> None:
    if name not in ALLOWED_FILES:
        raise HTTPException(status_code=404, detail=f"unknown config file: {name!r}")


def _validate(name: str, content: str) -> tuple[bool, list[str], str | None]:
    """yaml-parses `content`, then checks it keeps the same top-level key set
    as the file currently on disk (generalizes across all five files without
    a hand-written schema per file, per the design doc)."""
    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        return False, [f"yaml parse error: {exc}"], None

    path = CONFIG_DIR / name
    current_raw = path.read_text(encoding="utf-8") if path.exists() else ""
    current_parsed = yaml.safe_load(current_raw) if current_raw else None

    if isinstance(current_parsed, dict):
        current_keys = set(current_parsed.keys())
        proposed_keys = set(parsed.keys()) if isinstance(parsed, dict) else set()
        missing, added = current_keys - proposed_keys, proposed_keys - current_keys
        if missing or added:
            errors = []
            if missing:
                errors.append(f"missing top-level keys: {sorted(missing)}")
            if added:
                errors.append(f"unexpected top-level keys: {sorted(added)}")
            return False, errors, None

    diff = "".join(
        difflib.unified_diff(
            current_raw.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=name,
            tofile=f"{name} (proposed)",
        )
    )
    return True, [], diff


@router.get("/config")
def list_config() -> dict:
    return {"files": ALLOWED_FILES}


@router.get("/config/{name}")
def get_config(name: str) -> dict:
    _require_known(name)
    path = CONFIG_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"config file not found on disk: {name!r}")
    raw = path.read_text(encoding="utf-8")
    return {"name": name, "raw": raw, "parsed": yaml.safe_load(raw)}


@router.post("/config/{name}/preview")
def preview_config(name: str, body: PreviewRequest) -> dict:
    _require_known(name)
    valid, errors, diff = _validate(name, body.content)
    return {"valid": valid, "errors": errors, "diff": diff}


@router.post("/config/{name}/apply")
def apply_config(name: str, body: ApplyRequest) -> dict:
    _require_known(name)
    if body.confirm is not True:
        raise HTTPException(status_code=400, detail="confirm must be true")
    valid, errors, _ = _validate(name, body.content)
    if not valid:
        raise HTTPException(status_code=400, detail={"valid": False, "errors": errors})
    path = CONFIG_DIR / name
    path.write_text(body.content, encoding="utf-8")
    load_yaml.cache_clear()
    return {"written": True, "path": f"config/{name}"}
