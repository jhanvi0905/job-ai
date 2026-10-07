"""Himalayas Remote Jobs API adapter. Public, unauthenticated, free:
https://himalayas.app/jobs/api/search — a cross-company remote-job
aggregator, unlike the other adapters which are one board per company.

Their docs explicitly say the data refreshes every 24h and there's no
benefit polling more than once a day — a perfect match for our daily cron,
not a restriction against it. Verified live 2026-09-22: `offset`-based
pagination is silently broken on the /search endpoint (returns page 1
regardless of the offset value) despite being mentioned in the docs, so each
configured query reliably returns only its first ~20 results. Several
targeted keyword queries (see config/sources.yaml) compensate for that
rather than relying on one broad query.

Each entry's `identifier` is a raw querystring fragment, e.g.
"country=IN&q=AI+engineer" or "worldwide=true&q=machine+learning+engineer" —
not a company token, since this source spans many companies. Every returned
job carries its OWN company identity (companyName/companySlug), which is
what actually flows into RawJob.company_name — not the query's label.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

import requests

from jobai.engine.jobs.schemas import RawJob
from jobai.engine.sources.base import JobSource

logger = logging.getLogger(__name__)

SEARCH_URL = "https://himalayas.app/jobs/api/search"


class HimalayasSource(JobSource):
    def fetch_jobs(self) -> list[RawJob]:
        resp = requests.get(f"{SEARCH_URL}?{self.identifier}", timeout=15)
        resp.raise_for_status()
        payload = resp.json()

        jobs: list[RawJob] = []
        for item in payload.get("jobs", []):
            try:
                jobs.append(self._to_raw_job(item))
            except Exception:  # noqa: BLE001
                logger.warning(
                    "himalayas: skipping malformed posting guid=%s for query '%s'",
                    item.get("guid"),
                    self.identifier,
                    exc_info=True,
                )
        return jobs

    def _to_raw_job(self, item: dict) -> RawJob:
        restrictions = item.get("locationRestrictions") or []
        # Reuses the existing text-based eligibility logic in filters.py
        # unchanged: "Worldwide" trips the eligible_signals list, a country
        # list containing "India" trips candidate_country matching, a list
        # that excludes India trips location_named_regions/restrictive checks.
        location_text = "Worldwide" if not restrictions else ", ".join(restrictions)

        pub_date = item.get("pubDate")
        updated_at = (
            datetime.fromtimestamp(pub_date, tz=UTC).isoformat() if pub_date else None
        )

        return RawJob(
            source="himalayas",
            source_company_identifier=item.get("companySlug", item.get("companyName", "")),
            external_job_id=item["guid"],
            title=item.get("title", ""),
            company_name=item.get("companyName", "Unknown"),
            location=location_text,
            description_html=item.get("description") or item.get("excerpt"),
            absolute_url=item.get("applicationLink"),
            updated_at=updated_at,
            metadata={
                "workplace_type": "Remote",  # Himalayas is a remote-only board by definition
                "employment_type": item.get("employmentType"),
            },
            raw_payload=item,
        )
