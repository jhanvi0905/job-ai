"""One user journey across API + services: signup -> prefs -> resume -> feed refresh
-> job detail -> tracker -> usage. Proves the layers are wired together, not just
individually correct; two tenants confirm the feed is never shared."""
from __future__ import annotations

from jobai.engine.jobs.fingerprint import compute_description_hash
from jobai.engine.jobs.schemas import NormalizedJob
from jobai.product.db.models import Job
from jobai.product.services.catalog import _apply
from tests.product import api_helpers  # noqa: F401
from tests.product.api_helpers import PARSED, FakeLLM, app, client, drain, llm, session_factory, signup, upload  # noqa: F401, F811
from tests.product.conftest import CLASSIFY_OK, MATCH_STRONG


def _add_job(session_factory, n: int, location: str) -> int:
    desc = "Build LLM and RAG systems in Python."
    nj = NormalizedJob(
        external_job_id=str(n), source="greenhouse", source_company_identifier="acme", company_name=f"Acme{n}",
        title="Senior ML Engineer", location=location, workplace_type="Remote", description=desc,
        job_url=f"https://x/{n}", application_url=f"https://x/{n}", job_fingerprint=f"greenhouse:{n}",
        description_hash=compute_description_hash(desc),
    )
    with session_factory() as s:
        row = Job(fingerprint=nj.job_fingerprint, active=True)
        _apply(row, nj)
        s.add(row)
        s.commit()
        return row.id


def test_full_journey(client, app, session_factory):
    app.state.provider_factory = lambda uid, rid: FakeLLM(
        {"parse_resume": PARSED, "classify_job": CLASSIFY_OK, "analyse_match": MATCH_STRONG})
    job_id = _add_job(session_factory, 1, "Canada")
    h = signup(client)

    assert client.put("/prefs", headers=h, json={"countries": ["Canada"], "total_years": 4}).status_code == 200
    assert upload(client, h).status_code == 201

    queued = client.post("/feed/refresh", headers=h)
    assert queued.status_code == 202 and queued.json()["status"] == "queued"
    # A second click while it is queued returns the same task (deduplicated).
    assert client.post("/feed/refresh", headers=h).json()["task_id"] == queued.json()["task_id"]
    drain(client)  # what the worker process does
    task = client.get(f"/tasks/{queued.json()['task_id']}", headers=h).json()
    assert task["status"] == "succeeded" and task["kind"] == "feed_refresh" and task["finished_at"]
    summary = task["result"]
    assert summary["considered"] >= 1 and summary["errored"] == 0

    items = client.get("/feed", headers=h).json()["items"]
    assert [i["job_id"] for i in items] == [job_id]
    assert items[0]["fit"] in {"strong", "plausible"}

    detail = client.get(f"/jobs/{job_id}", headers=h).json()
    assert detail["evaluation"] is not None

    assert client.put(f"/applications/{job_id}", headers=h, json={"status": "saved"}).status_code == 200
    assert [a["job_id"] for a in client.get("/applications", headers=h).json()] == [job_id]
    assert client.get("/usage", headers=h).json()["plan"] == "free"

    other = signup(client, "b@example.com")
    assert client.get("/feed", headers=other).json()["items"] == []
    assert client.get("/applications", headers=other).json() == []
