from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from jobai.engine.jobs.schemas import RawJob
from jobai.engine.sources.base import JobSource
from jobai.product.db.models import Job
from jobai.product.services.catalog import STALE_AFTER_DAYS, ingest_catalog

NOW = datetime(2026, 10, 1, tzinfo=UTC)


class StubSource(JobSource):
    def __init__(self, jobs=None, error=None, identifier="stub"):
        self.company_name, self.identifier = "Acme", identifier
        self._jobs, self._error = jobs or [], error

    def fetch_jobs(self):
        if self._error:
            raise self._error
        return self._jobs


def raw(i="1", description="<p>Build LLM systems</p>", title="ML Engineer") -> RawJob:
    return RawJob(source="greenhouse", source_company_identifier="acme", external_job_id=i, title=title,
                  company_name="Acme", location="Remote", description_html=description,
                  absolute_url=f"https://x/{i}", updated_at="2026-09-30T00:00:00Z")


def test_insert_then_idempotent(session):
    src = StubSource([raw("1"), raw("2")])
    first = ingest_catalog(session, [src], now=NOW)
    assert (first.inserted, first.unchanged) == (2, 0)
    second = ingest_catalog(session, [src], now=NOW + timedelta(days=1))
    assert (second.inserted, second.updated, second.unchanged) == (0, 0, 2)
    rows = session.scalars(select(Job)).all()
    assert len(rows) == 2 and all(r.last_seen_at.replace(tzinfo=UTC) == NOW + timedelta(days=1) for r in rows)


def test_changed_description_updates_row(session):
    ingest_catalog(session, [StubSource([raw("1")])], now=NOW)
    summary = ingest_catalog(session, [StubSource([raw("1", description="<p>Totally new text</p>")])], now=NOW)
    assert summary.updated == 1
    row = session.scalar(select(Job))
    assert row.description == "Totally new text" and row.normalized["description"] == "Totally new text"
    assert "raw_source_payload" not in row.normalized


def test_unseen_jobs_go_inactive_and_come_back(session):
    ingest_catalog(session, [StubSource([raw("1"), raw("2")])], now=NOW)
    later = NOW + timedelta(days=STALE_AFTER_DAYS + 1)
    summary = ingest_catalog(session, [StubSource([raw("1")])], now=later)
    assert summary.deactivated == 1
    assert {r.external_id: r.active for r in session.scalars(select(Job))} == {"1": True, "2": False}
    back = ingest_catalog(session, [StubSource([raw("2")])], now=later)
    assert back.reactivated == 1 and session.scalar(select(Job).where(Job.external_id == "2")).active


def test_failing_source_does_not_fail_run_or_deactivate(session):
    ingest_catalog(session, [StubSource([raw("1")])], now=NOW)
    summary = ingest_catalog(session, [StubSource(error=RuntimeError("boom")), StubSource([raw("9")], identifier="ok")],
                             now=NOW + timedelta(days=2))
    assert summary.inserted == 1 and len(summary.source_errors) == 1
    assert session.scalar(select(Job).where(Job.external_id == "1")).active  # not seen, but within the window


def test_in_batch_duplicates_collapse(session):
    summary = ingest_catalog(session, [StubSource([raw("1"), raw("1")])], now=NOW)
    assert summary.inserted == 1
