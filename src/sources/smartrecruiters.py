"""SmartRecruiters Posting API adapter. Public, unauthenticated:
https://api.smartrecruiters.com/v1/companies/{company}/postings"""
from __future__ import annotations

import logging

import requests

from src.jobs.schemas import RawJob
from src.sources.base import JobSource

logger = logging.getLogger(__name__)

BASE_URL = "https://api.smartrecruiters.com/v1/companies"


class SmartRecruitersSource(JobSource):
    def fetch_jobs(self) -> list[RawJob]:
        url = f"{BASE_URL}/{self.identifier}/postings"
        jobs: list[RawJob] = []
        page = 0
        while True:
            resp = requests.get(url, params={"offset": page * 100, "limit": 100}, timeout=15)
            resp.raise_for_status()
            payload = resp.json()
            content = payload.get("content", [])
            if not content:
                break
            for item in content:
                try:
                    jobs.append(self._to_raw_job(item))
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "smartrecruiters: skipping malformed posting id=%s for %s",
                        item.get("id"),
                        self.identifier,
                        exc_info=True,
                    )
            if len(content) < 100:
                break
            page += 1
        return jobs

    def _to_raw_job(self, item: dict) -> RawJob:
        location = item.get("location", {}) or {}
        location_str = ", ".join(
            filter(None, [location.get("city"), location.get("region"), location.get("country")])
        ) or None
        return RawJob(
            source="smartrecruiters",
            source_company_identifier=self.identifier,
            external_job_id=str(item["id"]),
            title=item.get("name", ""),
            company_name=self.company_name,
            location=location_str,
            description_html=None,  # requires a second call to the posting detail endpoint
            absolute_url=(item.get("applyUrl") or {}).get("url") if isinstance(item.get("applyUrl"), dict) else item.get("ref"),
            updated_at=item.get("releasedDate"),
            metadata={"remote": location.get("remote")},
            raw_payload=item,
        )
