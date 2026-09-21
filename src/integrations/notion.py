"""Notion integration. Extends the existing Job Pipeline database — never
creates a second one (PRD §21). Uses the official REST API with an internal
integration token; see README for one-time setup (create the integration,
share the Job Pipeline database with it).

Dedup cache lives IN Notion (Job Fingerprint / JD Hash columns) rather than a
separate local store — PRD §5 explicitly rules out a second duplicate-tracking
system outside Notion.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from typing import Optional

import requests

NOTION_VERSION = "2022-06-28"
API_BASE = "https://api.notion.com/v1"

# Discovered once via Phase 0 inspection (Jhanvi — Life OS / Domains / Job Search).
# Override via env if the database is ever recreated.
DEFAULT_JOB_PIPELINE_DB_ID = ""


class NotionClient:
    def __init__(self, api_key: Optional[str] = None, database_id: Optional[str] = None):
        self.api_key = api_key or os.environ["NOTION_API_KEY"]
        self.database_id = database_id or os.environ.get(
            "NOTION_JOB_PIPELINE_DB_ID", DEFAULT_JOB_PIPELINE_DB_ID
        )
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            }
        )

    def find_by_fingerprint(self, job_fingerprint: str) -> Optional[dict]:
        """Return the existing page for this fingerprint, or None."""
        resp = self.session.post(
            f"{API_BASE}/databases/{self.database_id}/query",
            json={
                "filter": {
                    "property": "Job Fingerprint",
                    "rich_text": {"equals": job_fingerprint},
                },
                "page_size": 1,
            },
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0] if results else None

    def get_plain_by_fingerprint(self, job_fingerprint: str) -> Optional[dict]:
        """Same lookup as find_by_fingerprint, flattened to plain values —
        what analyse_job() needs (Company, Role, Job URL) without parsing
        raw Notion property JSON itself."""
        page = self.find_by_fingerprint(job_fingerprint)
        return _page_to_plain_dict(page) if page else None

    def create_job_page(self, properties: dict) -> dict:
        resp = self.session.post(
            f"{API_BASE}/pages",
            json={
                "parent": {"database_id": self.database_id},
                "properties": _to_notion_properties(properties),
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def update_job_page(self, page_id: str, properties: dict) -> dict:
        resp = self.session.patch(
            f"{API_BASE}/pages/{page_id}",
            json={"properties": _to_notion_properties(properties)},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def query_priority_jobs(self, limit: int = 15) -> list[dict]:
        """The 'Jobs to Review' queue (PRD §37): open pipeline statuses only,
        sorted by Priority then Date Posted — read-only, no writes."""
        resp = self.session.post(
            f"{API_BASE}/databases/{self.database_id}/query",
            json={
                "filter": {
                    "property": "Status",
                    "select": {"is_not_empty": True},
                },
                "sorts": [
                    {"property": "Priority", "direction": "ascending"},
                    {"property": "Date Posted", "direction": "descending"},
                ],
                "page_size": limit,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return [_page_to_plain_dict(p) for p in resp.json().get("results", [])]


def _plain_value(prop: dict):
    ptype = prop.get("type")
    if ptype == "title":
        return "".join(t["plain_text"] for t in prop["title"]) or None
    if ptype == "rich_text":
        return "".join(t["plain_text"] for t in prop["rich_text"]) or None
    if ptype == "select":
        return prop["select"]["name"] if prop["select"] else None
    if ptype == "url":
        return prop.get("url")
    if ptype == "date":
        return prop["date"]["start"] if prop["date"] else None
    return None


def _page_to_plain_dict(page: dict) -> dict:
    """Flattens a Notion page into plain field:value pairs — the shape a
    future caller (MCP tool, HTTP handler) actually wants, not raw Notion JSON."""
    out = {"notion_page_id": page["id"], "notion_url": page.get("url")}
    for name, prop in page.get("properties", {}).items():
        out[name] = _plain_value(prop)
    return out


def _rich_text(value: str) -> dict:
    # Notion rich_text has a 2000-char-per-block limit; truncate defensively
    # rather than let a long JD crash the write.
    return {"rich_text": [{"text": {"content": (value or "")[:1990]}}]}


def _to_notion_properties(props: dict) -> dict:
    """Maps our plain-Python property dict to Notion's typed property
    payloads. Keys must exactly match the Job Pipeline schema field names."""
    out: dict = {}
    for key, value in props.items():
        if value is None:
            continue
        if key == "Opportunity":  # title
            out[key] = {"title": [{"text": {"content": value}}]}
        elif key in {"Job URL"}:
            out[key] = {"url": value}
        elif key in {"Status", "Priority", "Source", "Source Channel", "Work Mode", "Role Family", "Fit Band", "Action Mode"}:
            out[key] = {"select": {"name": value}}
        elif key in {"Found Date", "Date Posted", "Last Checked", "Last Analysed", "Applied Date"}:
            if isinstance(value, (date, datetime)):
                value = value.isoformat()
            out[key] = {"date": {"start": value}}
        else:
            out[key] = _rich_text(str(value))
    return out
