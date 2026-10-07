"""Dashboard API tests. Never hits a real capability, real Notion, or the
real data/ledger.db / config/ files — everything is monkeypatched or faked."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from jobai.assistant.dashboard_api.app import app
from jobai.assistant.dashboard_api.routers import config as config_router
from jobai.assistant.dashboard_api.routers import runs as runs_router
from jobai.assistant.workflows.inbox import InboxSummary
from jobai.core.ledger.db import Ledger
from jobai.core.telemetry.logging import RunSummary

ADMIN = "test-admin-token"
client = TestClient(app, headers={"Authorization": f"Bearer {ADMIN}"})


@pytest.fixture(autouse=True)
def _admin_token(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", ADMIN)


# --------------------------------------------------------------------------
# admin auth (every route)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": f"Basic {ADMIN}"}])
def test_every_route_requires_admin_token(headers):
    anon = TestClient(app)
    for method, path in [("get", "/api/config"), ("get", "/api/runs"), ("get", "/api/health-check"),
                         ("post", "/api/config/career_rules.yaml/preview")]:
        assert getattr(anon, method)(path, headers=headers).status_code == 401, path


def test_without_token_dev_serves_loopback_only(monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN")
    monkeypatch.setenv("APP_ENV", "dev")
    assert TestClient(app).get("/api/health-check").status_code == 401  # TestClient's peer is "testclient"
    assert TestClient(app, client=("127.0.0.1", 5000)).get("/api/health-check").status_code == 200


def test_refuses_to_start_outside_dev_without_token(monkeypatch):
    from jobai.assistant.dashboard_api.app import create_app
    monkeypatch.delenv("ADMIN_TOKEN")
    monkeypatch.setenv("APP_ENV", "prod")
    with pytest.raises(RuntimeError, match="ADMIN_TOKEN"):
        create_app()
    monkeypatch.setenv("ADMIN_TOKEN", "x")
    assert create_app().openapi_url is None  # no schema/docs outside dev


# --------------------------------------------------------------------------
# config endpoints
# --------------------------------------------------------------------------

FIXTURE_YAML = "experience: 3\nseniority: mid\n"


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    d = tmp_path / "config"
    d.mkdir()
    (d / "career_rules.yaml").write_text(FIXTURE_YAML, encoding="utf-8")
    monkeypatch.setattr(config_router, "CONFIG_DIR", d)
    return d


def test_list_config_returns_the_five_hardcoded_files():
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json() == {"files": config_router.ALLOWED_FILES}


def test_get_config_file(config_dir):
    resp = client.get("/api/config/career_rules.yaml")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"name": "career_rules.yaml", "raw": FIXTURE_YAML, "parsed": {"experience": 3, "seniority": "mid"}}


def test_get_config_rejects_unknown_name(config_dir):
    resp = client.get("/api/config/not_a_real_file.yaml")
    assert resp.status_code == 404


def test_get_config_rejects_path_traversal(config_dir):
    resp = client.get("/api/config/..%2F..%2Fetc%2Fpasswd")
    assert resp.status_code == 404


def test_preview_valid_change_includes_diff(config_dir):
    new_content = "experience: 5\nseniority: mid\n"
    resp = client.post("/api/config/career_rules.yaml/preview", json={"content": new_content})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["errors"] == []
    assert body["diff"] and "experience" in body["diff"]


def test_preview_with_a_key_removed_is_invalid(config_dir):
    resp = client.post("/api/config/career_rules.yaml/preview", json={"content": "seniority: mid\n"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert body["diff"] is None
    assert any("experience" in e for e in body["errors"])


def test_preview_broken_yaml_is_invalid(config_dir):
    resp = client.post("/api/config/career_rules.yaml/preview", json={"content": "experience: [unterminated"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert body["diff"] is None
    assert any("yaml parse error" in e for e in body["errors"])


def test_apply_with_confirm_true_writes_and_is_readable_back(config_dir):
    new_content = "experience: 7\nseniority: senior\n"
    resp = client.post("/api/config/career_rules.yaml/apply", json={"content": new_content, "confirm": True})
    assert resp.status_code == 200
    assert resp.json() == {"written": True, "path": "config/career_rules.yaml"}
    assert (config_dir / "career_rules.yaml").read_text(encoding="utf-8") == new_content
    assert client.get("/api/config/career_rules.yaml").json()["raw"] == new_content


def test_apply_without_confirm_is_rejected_and_file_unchanged(config_dir):
    original = (config_dir / "career_rules.yaml").read_text(encoding="utf-8")
    changed = "experience: 9\nseniority: mid\n"

    resp = client.post("/api/config/career_rules.yaml/apply", json={"content": changed})
    assert resp.status_code == 400
    assert (config_dir / "career_rules.yaml").read_text(encoding="utf-8") == original

    resp2 = client.post("/api/config/career_rules.yaml/apply", json={"content": changed, "confirm": False})
    assert resp2.status_code == 400
    assert (config_dir / "career_rules.yaml").read_text(encoding="utf-8") == original


def test_apply_rejects_invalid_content_even_with_confirm(config_dir):
    original = (config_dir / "career_rules.yaml").read_text(encoding="utf-8")
    resp = client.post("/api/config/career_rules.yaml/apply", json={"content": "seniority: mid\n", "confirm": True})
    assert resp.status_code == 400
    assert (config_dir / "career_rules.yaml").read_text(encoding="utf-8") == original


# --------------------------------------------------------------------------
# runs / health / calibration endpoints
# --------------------------------------------------------------------------


@pytest.fixture
def seeded_ledger(monkeypatch):
    ledger = Ledger.memory()
    run_a = ledger.start_run("discovery", budget_usd=0.3, config_signature="sig1")
    ledger.record_call(run_id=run_a, node="triage", attempt=1, model_requested="gpt-test", outcome="ok", cost_usd=0.002)
    ledger.record_funnel(run_a, "write", {"written_new": 3})
    ledger.finish_run(run_a, "ok")

    run_b = ledger.start_run("inbox")
    ledger.finish_run(run_b, "failed", note="boom")

    monkeypatch.setattr(runs_router, "get_ledger", lambda: ledger)
    return ledger, run_a, run_b


def test_list_runs(seeded_ledger):
    ledger, run_a, run_b = seeded_ledger
    resp = client.get("/api/runs?limit=10")
    assert resp.status_code == 200
    rows = {r["run_id"]: r for r in resp.json()}
    assert run_a in rows and run_b in rows
    assert rows[run_a]["graph"] == "discovery"
    assert rows[run_a]["status"] == "ok"
    assert rows[run_a]["budget_usd"] == 0.3
    assert rows[run_b]["status"] == "failed"
    assert rows[run_b]["note"] == "boom"


def test_get_run_detail(seeded_ledger):
    ledger, run_a, _ = seeded_ledger
    resp = client.get(f"/api/runs/{run_a}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == run_a
    assert len(body["llm_calls"]) == 1
    assert body["llm_calls"][0]["node"] == "triage"
    assert len(body["funnel"]) == 1
    assert body["funnel"][0]["reason_code"] == "written_new"
    # empty item-level event chain for this run -> nothing unaccounted for
    assert body["conservation_ok"] is True


def test_get_run_detail_404_for_unknown_run(seeded_ledger):
    resp = client.get("/api/runs/no-such-run")
    assert resp.status_code == 404


def test_health_endpoint_calls_ledger_health_check(seeded_ledger):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    findings = resp.json()
    assert isinstance(findings, list) and findings
    assert all({"level", "name", "message"} <= set(f) for f in findings)
    assert any(f["name"] == "runs" for f in findings)


def test_calibration_endpoint_includes_text(seeded_ledger):
    resp = client.get("/api/calibration")
    assert resp.status_code == 200
    body = resp.json()
    assert body["approved"] == 0
    assert isinstance(body["text"], str) and body["text"]


def test_health_check_liveness():
    resp = client.get("/api/health-check")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# --------------------------------------------------------------------------
# trigger endpoints
# --------------------------------------------------------------------------


def test_trigger_preview_discover_jobs_passes_dry_run_true():
    fake_summary = RunSummary(run_id="r1", fetched=5)
    with patch("jobai.assistant.dashboard_api.routers.runs.discover_jobs", return_value=fake_summary) as mock_fn:
        resp = client.post("/api/runs/trigger/preview", json={"graph": "discover_jobs"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["dry_run"] is True
    assert body["summary"]["run_id"] == "r1"
    assert body["summary"]["fetched"] == 5
    mock_fn.assert_called_once_with(dry_run=True)


def test_trigger_preview_sync_inbox_passes_dry_run_true():
    fake_summary = InboxSummary(run_id="r2", fetched=3, processed=2)
    with patch("jobai.assistant.dashboard_api.routers.runs.sync_inbox", return_value=fake_summary) as mock_fn:
        resp = client.post("/api/runs/trigger/preview", json={"graph": "sync_inbox"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["dry_run"] is True
    assert body["summary"]["processed"] == 2
    mock_fn.assert_called_once_with(dry_run=True)


def test_trigger_preview_catches_exception_instead_of_raising():
    with patch("jobai.assistant.dashboard_api.routers.runs.discover_jobs", side_effect=RuntimeError("boom")):
        resp = client.post("/api/runs/trigger/preview", json={"graph": "discover_jobs"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "boom" in body["error"]


def test_trigger_confirm_requires_confirm_true_and_never_calls_capability():
    with patch("jobai.assistant.dashboard_api.routers.runs.discover_jobs") as mock_fn:
        resp = client.post("/api/runs/trigger/confirm", json={"graph": "discover_jobs"})
        assert resp.status_code == 400
        resp2 = client.post("/api/runs/trigger/confirm", json={"graph": "discover_jobs", "confirm": False})
        assert resp2.status_code == 400
    mock_fn.assert_not_called()


def test_trigger_confirm_calls_capability_with_dry_run_false():
    fake_summary = RunSummary(run_id="r3")
    with patch("jobai.assistant.dashboard_api.routers.runs.discover_jobs", return_value=fake_summary) as mock_fn:
        resp = client.post("/api/runs/trigger/confirm", json={"graph": "discover_jobs", "confirm": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["dry_run"] is False
    mock_fn.assert_called_once_with(dry_run=False)
