"""Ashby Job Posting API adapter. Public, unauthenticated, keyless:
https://api.ashbyhq.com/posting-api/job-board/{company} — returns the whole
board in one call. Many AI-native startups (RF04 territory) use Ashby rather
than Greenhouse/Lever, so this meaningfully widens coverage.

Unlike Greenhouse/Lever, Ashby returns structured workplaceType/isRemote/
addressCountry fields instead of free-text-only location — normalize.py uses
these directly when present instead of guessing from text (see
NormalizedJob.location_country / RawJob.metadata['workplace_type'])."""
from __future__ import annotations

import logging

import requests

from src.jobs.schemas import RawJob
from src.sources.base import JobSource

logger = logging.getLogger(__name__)

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board"


class AshbySource(JobSource):
    def fetch_jobs(self) -> list[RawJob]:
        url = f"{BASE_URL}/{self.identifier}"
        resp = requests.get(url, params={"includeCompensation": "false"}, timeout=15)
        resp.raise_for_status()
        payload = resp.json()

        jobs: list[RawJob] = []
        for item in payload.get("jobs", []):
            try:
                jobs.append(self._to_raw_job(item))
            except Exception:  # noqa: BLE001
                logger.warning(
                    "ashby: skipping malformed posting id=%s for %s",
                    item.get("id"),
                    self.identifier,
                    exc_info=True,
                )
        return jobs

    def _to_raw_job(self, item: dict) -> RawJob:
        address = (item.get("address") or {}).get("postalAddress") or {}
        return RawJob(
            source="ashby",
            source_company_identifier=self.identifier,
            external_job_id=str(item["id"]),
            title=item.get("title", ""),
            company_name=self.company_name,
            location=item.get("location"),
            description_html=item.get("descriptionHtml") or item.get("descriptionPlain"),
            absolute_url=item.get("jobUrl"),
            updated_at=item.get("publishedAt"),
            metadata={
                "workplace_type": item.get("workplaceType"),  # "Remote" | "Hybrid" | "OnSite"
                "is_remote": item.get("isRemote"),
                "location_country": address.get("addressCountry"),
                "department": item.get("department"),
            },
            raw_payload=item,
        )
