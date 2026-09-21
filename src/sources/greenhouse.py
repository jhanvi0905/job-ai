"""Greenhouse Job Board API adapter. Public, unauthenticated, one board token
per company: https://boards-api.greenhouse.io/v1/boards/{token}/jobs"""
from __future__ import annotations

import logging

import requests

from src.jobs.schemas import RawJob
from src.sources.base import JobSource

logger = logging.getLogger(__name__)

BASE_URL = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseSource(JobSource):
    def fetch_jobs(self) -> list[RawJob]:
        url = f"{BASE_URL}/{self.identifier}/jobs"
        resp = requests.get(url, params={"content": "true"}, timeout=15)
        resp.raise_for_status()
        payload = resp.json()

        jobs: list[RawJob] = []
        for item in payload.get("jobs", []):
            try:
                jobs.append(self._to_raw_job(item))
            except Exception:  # noqa: BLE001 — one bad posting must not kill the batch
                logger.warning(
                    "greenhouse: skipping malformed posting id=%s for %s",
                    item.get("id"),
                    self.identifier,
                    exc_info=True,
                )
        return jobs

    def _to_raw_job(self, item: dict) -> RawJob:
        location = (item.get("location") or {}).get("name")
        return RawJob(
            source="greenhouse",
            source_company_identifier=self.identifier,
            external_job_id=str(item["id"]),
            title=item.get("title", ""),
            company_name=self.company_name,
            location=location,
            description_html=item.get("content"),
            absolute_url=item.get("absolute_url"),
            updated_at=item.get("updated_at"),
            metadata={
                "departments": [d.get("name") for d in item.get("departments", [])],
                "offices": [o.get("name") for o in item.get("offices", [])],
            },
            raw_payload=item,
        )
