"""Lever Postings API adapter. Public, unauthenticated:
https://api.lever.co/v0/postings/{company}?mode=json"""
from __future__ import annotations

import logging

import requests

from jobai.engine.jobs.schemas import RawJob
from jobai.engine.sources.base import JobSource

logger = logging.getLogger(__name__)

BASE_URL = "https://api.lever.co/v0/postings"


class LeverSource(JobSource):
    def fetch_jobs(self) -> list[RawJob]:
        url = f"{BASE_URL}/{self.identifier}"
        resp = requests.get(url, params={"mode": "json"}, timeout=15)
        resp.raise_for_status()
        payload = resp.json()

        jobs: list[RawJob] = []
        for item in payload:
            try:
                jobs.append(self._to_raw_job(item))
            except Exception:  # noqa: BLE001
                logger.warning(
                    "lever: skipping malformed posting id=%s for %s",
                    item.get("id"),
                    self.identifier,
                    exc_info=True,
                )
        return jobs

    def _to_raw_job(self, item: dict) -> RawJob:
        categories = item.get("categories", {}) or {}
        description = item.get("descriptionPlain") or item.get("description") or ""
        return RawJob(
            source="lever",
            source_company_identifier=self.identifier,
            external_job_id=str(item["id"]),
            title=item.get("text", ""),
            company_name=self.company_name,
            location=categories.get("location"),
            description_html=description,
            absolute_url=item.get("hostedUrl"),
            updated_at=str(item.get("createdAt")) if item.get("createdAt") else None,
            metadata={
                "commitment": categories.get("commitment"),
                "team": categories.get("team"),
            },
            raw_payload=item,
        )
