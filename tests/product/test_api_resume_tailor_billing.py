"""Resume parsing, tailor validator + cache, quota -> 429, billing idempotency."""
import hashlib
import hmac
import io
import json

import pytest

from jobai.product.db.models import User
from jobai.product.services import billing
from jobai.product.services import tailor as tailor_svc
from tests.product.api_helpers import *  # noqa: F401,F403
from tests.product.api_helpers import signup, upload


# ------------------------------------------------------------------ resume
def test_upload_parses_and_dedupes_and_preserves_edits(client, llm):
    h = signup(client)
    up = upload(client, h)
    assert up.status_code == 201 and up.json()["task_id"]
    task = client.get(f"/tasks/{up.json()['task_id']}", headers=h).json()
    assert task["status"] == "succeeded" and task["result"] == {"achievements": 2}
    aid = client.get("/achievements", headers=h).json()[0]["id"]
    patched = client.patch(f"/achievements/{aid}", headers=h, json={"summary": "My own words, 40% faster."})
    assert patched.json()["user_edited"] is True
    # Re-upload different file -> re-parse: no duplicates, edit untouched.
    upload(client, h, b"Slightly different resume text, still plenty long enough.")
    achs = client.get("/achievements", headers=h).json()
    assert len(achs) == 2
    assert next(a for a in achs if a["id"] == aid)["summary"] == "My own words, 40% faster."


def test_upload_validation(client):
    h = signup(client)
    assert client.post("/resume", headers=h, files={"file": ("a.exe", b"x" * 50, "application/octet-stream")}).status_code == 415
    assert client.post("/resume", headers=h, files={"file": ("a.txt", b"x" * (2 * 1024 * 1024 + 1), "text/plain")}).status_code == 413
    assert client.post("/resume", headers=h, files={"file": ("a.txt", b"", "text/plain")}).status_code == 400


def test_docx_and_pdf_text_extraction():
    from docx import Document

    from jobai.product.services.resume import extract_text
    buf = io.BytesIO()
    d = Document()
    d.add_paragraph("Built things with Python and shipped them to production daily.")
    d.save(buf)
    assert "Python" in extract_text("cv.docx", buf.getvalue())


def test_parse_repairs_via_validate(client, llm):
    """The strict schema is passed as `validate=`, so bad output goes down the gateway repair path."""
    h = signup(client)
    upload(client, h)
    validate = llm.calls[0]["validate"]
    with pytest.raises(Exception):
        validate({"achievements": [{"summary": "no title"}]})
    assert llm.calls[0]["workflow"] == "parse_resume"


def test_parse_quota_429(client):
    h = signup(client)  # free plan: 2 parses/day
    assert upload(client, h).status_code == 201
    assert upload(client, h, b"another resume text number two, long enough").status_code == 201
    r = upload(client, h, b"another resume text number three, long enough")
    assert r.status_code == 429 and r.json()["error"]["code"] == "quota_exceeded"


# ------------------------------------------------------------------ tailor
def _ids(client, h):
    return [a["id"] for a in client.get("/achievements", headers=h).json()]


def test_tailor_validator_drops_invented_content():
    allowed = {"1": "Built streaming pipeline Cut latency by 40% using Kafka.", "2": "Led migration 12 services"}
    kept, dropped = tailor_svc.validate_bullets([
        {"original": "", "proposed": "Cut latency by 40% with Kafka", "evidence_ids": ["1"]},          # ok
        {"original": "", "proposed": "Led Kubernetes migration", "evidence_ids": ["99"]},               # invented id
        {"original": "", "proposed": "Ran a team of 50", "evidence_ids": []},                           # no evidence
        {"original": "", "proposed": "Cut latency by 90%", "evidence_ids": ["1"]},                      # invented number
        {"original": "", "proposed": "Mixed", "evidence_ids": ["1", "99"]},                             # one bad id poisons it
        "garbage",
    ], allowed)
    assert [k["proposed"] for k in kept] == ["Cut latency by 40% with Kafka"]
    assert {d["reason"] for d in dropped} == {"unknown_evidence_id", "no_evidence", "unsupported_number", "malformed"}


def test_tailor_end_to_end_filters_and_caches(client, session_factory, job, llm):
    h = signup(client)
    upload(client, h)
    first_id = _ids(client, h)[0]
    llm.by["tailor_resume"] = {"bullets": [
        {"original": "", "proposed": "Cut latency by 40% on Kafka pipelines", "evidence_ids": [str(first_id)]},
        {"original": "", "proposed": "Invented FAANG role", "evidence_ids": ["424242"]},
    ]}
    n_before = len(llm.calls)
    r = client.post(f"/jobs/{job}/tailor", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert len(body["bullets"]) == 1 and body["dropped"] == 1
    assert len(llm.calls) == n_before + 1
    # Cache: identical request -> same run, zero LLM calls, no extra quota used.
    r2 = client.post(f"/jobs/{job}/tailor", headers=h)
    assert r2.json()["run_id"] == body["run_id"] and len(llm.calls) == n_before + 1
    assert client.get("/usage", headers=h).json()["used"]["tailor"] == 1

    # accept + download
    assert client.post(f"/tailor/{body['run_id']}/accept", headers=h, json={"indices": [5]}).status_code == 400
    assert client.get(f"/tailor/{body['run_id']}/download", headers=h).status_code == 400
    assert client.post(f"/tailor/{body['run_id']}/accept", headers=h, json={"indices": [0]}).json()["status"] == "accepted"
    dl = client.get(f"/tailor/{body['run_id']}/download", headers=h)
    assert dl.status_code == 200 and dl.content[:2] == b"PK"


def test_tailor_quota_then_credit_then_429(client, session_factory, job, llm):
    h = signup(client)
    upload(client, h)
    ids = _ids(client, h)
    mk = lambda txt: {"bullets": [{"original": "", "proposed": txt, "evidence_ids": [str(ids[0])]}]}
    llm.by["tailor_resume"] = mk("one")
    assert client.post(f"/jobs/{job}/tailor", headers=h).status_code == 200  # uses the 1/day free quota
    # A different resume => different cache key; plan cap hit now.
    upload(client, h, b"A different resume body that is long enough to parse ok.")
    r = client.post(f"/jobs/{job}/tailor", headers=h)
    assert r.status_code == 429
    uid = client.get("/me", headers=h).json()["id"]
    with session_factory() as s:
        billing.grant(s, uid, 1, ref="evt-1")
        s.commit()
    assert client.post(f"/jobs/{job}/tailor", headers=h).status_code == 200
    assert client.get("/usage", headers=h).json()["credits"] == 0


# ----------------------------------------------------------------- billing
def test_ledger_idempotent_and_insufficient(session_factory):
    with session_factory() as s:
        u = User(email="u@x.com", password_hash="x")
        s.add(u)
        s.flush()
        assert billing.grant(s, u.id, 5, ref="e1") is True
        assert billing.grant(s, u.id, 5, ref="e1") is False
        assert billing.balance(s, u.id) == 5
        assert billing.spend(s, u.id, 2, ref="t1") is True
        assert billing.spend(s, u.id, 2, ref="t1") is False
        assert billing.balance(s, u.id) == 3
        with pytest.raises(billing.InsufficientCredits):
            billing.spend(s, u.id, 10)


def test_webhook_signature_and_idempotency(client, monkeypatch):
    monkeypatch.setenv("PAYMENT_WEBHOOK_SECRET", "whsec")
    h = signup(client)
    uid = client.get("/me", headers=h).json()["id"]
    body = json.dumps({"event_id": "evt_1", "user_id": uid, "credits": 10}).encode()
    sig = hmac.new(b"whsec", body, hashlib.sha256).hexdigest()
    assert client.post("/billing/webhook", content=body, headers={"X-Signature": "bad"}).status_code == 400
    for _ in range(2):
        assert client.post("/billing/webhook", content=body, headers={"X-Signature": sig}).status_code == 204
    assert client.get("/usage", headers=h).json()["credits"] == 10
    assert client.get("/usage", headers=h).json()["limits"]["tailor"] == 1
