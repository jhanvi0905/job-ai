"""Read-only Gmail client over the REST API (no Google SDK needed at runtime).

Safety properties, by construction:
  * Scope is gmail.readonly — the token physically cannot send, delete or label.
  * Only message METADATA is requested (headers + Gmail's ~100-char snippet).
    Message bodies and attachments are never fetched.
  * The refresh token lives in a gitignored file; nothing secret is logged.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parseaddr
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
CREDENTIALS_PATH = DATA_DIR / "gmail_credentials.json"  # OAuth client, downloaded from Google Cloud
TOKEN_PATH = DATA_DIR / "gmail_token.json"              # refresh token, written by scripts/gmail_auth.py
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://gmail.googleapis.com/gmail/v1/users/me"
MAX_MESSAGES = 300


class GmailAuthError(RuntimeError):
    """Credentials missing, revoked or expired for good — a human has to re-run gmail_auth.py."""


@dataclass(frozen=True)
class Message:
    id: str
    thread_id: str
    sender_name: str
    sender_email: str
    subject: str
    snippet: str
    received_at: datetime

    @property
    def sender_domain(self) -> str:
        return self.sender_email.rsplit("@", 1)[-1].lower() if "@" in self.sender_email else ""


def _load_json(path: Path, what: str) -> dict:
    if not path.exists():
        raise GmailAuthError(f"{what} not found at {path}. Run scripts/gmail_auth.py (see its docstring).")
    return json.loads(path.read_text(encoding="utf-8"))


class GmailReader:
    def __init__(self, *, session=None, credentials_path: Path | None = None, token_path: Path | None = None,
                 sleep=time.sleep):
        self.session = session or requests.Session()
        self._creds_path = credentials_path or CREDENTIALS_PATH
        self._token_path = token_path or TOKEN_PATH
        self._sleep = sleep
        self._access_token: str | None = None

    # ---- auth --------------------------------------------------------------
    def _refresh(self) -> str:
        creds = _load_json(self._creds_path, "OAuth client file")
        client = creds.get("installed") or creds.get("web") or creds
        token = _load_json(self._token_path, "Gmail token")
        resp = self.session.post(
            TOKEN_URL,
            data={
                "client_id": client["client_id"], "client_secret": client["client_secret"],
                "refresh_token": token["refresh_token"], "grant_type": "refresh_token",
            },
            timeout=20,
        )
        if resp.status_code in (400, 401):  # invalid_grant: revoked / expired refresh token
            raise GmailAuthError("Google rejected the refresh token (revoked or expired). Re-run scripts/gmail_auth.py.")
        resp.raise_for_status()
        self._access_token = resp.json()["access_token"]
        return self._access_token

    def _get(self, path: str, params: dict | list) -> dict:
        for attempt in (1, 2, 3):
            if self._access_token is None:
                self._refresh()
            resp = self.session.get(f"{API}{path}", params=params, headers={"Authorization": f"Bearer {self._access_token}"}, timeout=20)
            if resp.status_code == 401:
                self._access_token = None  # expired access token: refresh once and retry
                if attempt == 3:
                    raise GmailAuthError("Gmail rejected a freshly refreshed token.")
                continue
            if resp.status_code in (429, 500, 502, 503) and attempt < 3:
                self._sleep(2 ** attempt)
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError("unreachable")

    # ---- reads -------------------------------------------------------------
    def list_message_ids(self, lookback_days: int) -> list[str]:
        query = f"newer_than:{int(lookback_days)}d -in:sent -in:drafts -in:chats -in:spam"
        ids: list[str] = []
        page_token = None
        while len(ids) < MAX_MESSAGES:
            params: dict = {"q": query, "maxResults": 100}
            if page_token:
                params["pageToken"] = page_token
            data = self._get("/messages", params)
            ids.extend(m["id"] for m in data.get("messages", []))
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return ids[:MAX_MESSAGES]

    def get_message(self, message_id: str) -> Message:
        data = self._get(
            f"/messages/{message_id}",
            [("format", "metadata"), ("metadataHeaders", "From"), ("metadataHeaders", "Subject")],
        )
        headers = {h["name"].lower(): h["value"] for h in data.get("payload", {}).get("headers", [])}
        name, email = parseaddr(headers.get("from", ""))
        received = datetime.fromtimestamp(int(data.get("internalDate", 0)) / 1000, tz=timezone.utc)
        return Message(
            id=data["id"], thread_id=data.get("threadId", ""), sender_name=name, sender_email=email.lower(),
            subject=re.sub(r"\s+", " ", headers.get("subject", "")).strip(),
            snippet=re.sub(r"\s+", " ", data.get("snippet", "")).strip(), received_at=received,
        )
