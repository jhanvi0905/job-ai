"""Resume ingestion: file -> text -> stored version -> structured evidence bank.

The achievement bank is the product's source of truth: tailoring may only cite
rows from it. So parsing is strict (schema-validated, gateway repair path) and
never destroys user work: rows the user edited are never overwritten, and
re-parsing the same content is a no-op (dedupe by content hash).
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Protocol

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from jobai.core.config import load_models
from jobai.core.paths import PROMPTS_DIR
from jobai.engine.ai.provider import LLMProvider
from jobai.product.db.models import Achievement, ResumeVersion
from jobai.product.services import quota

MAX_BYTES = 2 * 1024 * 1024
ALLOWED_EXTENSIONS = (".pdf", ".docx", ".txt")
MAX_TEXT_CHARS_TO_LLM = 15000
MAX_ACHIEVEMENTS = 30
PROMPT_VERSION = "parse_resume_v1"
PROMPT_PATH = PROMPTS_DIR / f"{PROMPT_VERSION}.txt"
TAG_FIELDS = ("role_families", "skills", "system_patterns", "seniority_signals", "business_signals", "leadership_signals")


class StorageError(RuntimeError):
    """Object storage failed (network/5xx). Maps to 502 at the API edge."""


class ResumeError(ValueError):
    """Bad upload (type/size/unreadable). Maps to 400/413/415 at the API edge."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ------------------------------------------------------------------ storage
class Storage(Protocol):
    def save(self, user_id: int, name: str, data: bytes) -> str: ...
    def load(self, key: str) -> bytes: ...
    def delete_user(self, user_id: int) -> None: ...


class LocalStorage:
    """Files under data/uploads/{user_id}/. Keys are '{user_id}/{name}' relative to root."""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.environ.get("UPLOAD_DIR", "data/uploads"))

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not p.is_relative_to(self.root.resolve()):
            raise ValueError("bad storage key")
        return p

    def save(self, user_id: int, name: str, data: bytes) -> str:
        key = f"{user_id}/{name}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def load(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete_user(self, user_id: int) -> None:
        shutil.rmtree(self._path(str(user_id)), ignore_errors=True)


class SupabaseStorage:
    """Supabase Storage over its REST API with the service-role key (backend only).

    Private bucket (default `resumes`); keys are '{user_id}/{uuid}-{name}', so a
    user's files share one prefix and erasure is list-then-delete on it. The
    bucket must exist and be private (create it in the dashboard or SQL)."""

    PAGE = 1000

    def __init__(self, base_url: str, service_role_key: str, bucket: str = "resumes", client: httpx.Client | None = None):
        self.base = f"{base_url.rstrip('/')}/storage/v1"
        self.bucket = bucket
        self._headers = {"apikey": service_role_key, "Authorization": f"Bearer {service_role_key}"}
        self._client = client or httpx.Client(timeout=30)

    @classmethod
    def from_env(cls) -> SupabaseStorage | None:
        url, key = os.environ.get("SUPABASE_URL", "").strip(), os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not (url and key):
            return None
        return cls(url, key, bucket=os.environ.get("SUPABASE_STORAGE_BUCKET", "resumes"))

    @staticmethod
    def _check_key(key: str) -> str:
        if not key or key.startswith("/") or ".." in key.split("/") or "\\" in key:
            raise ValueError("bad storage key")
        return key

    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        try:
            r = self._client.request(method, f"{self.base}{path}", headers={**self._headers, **kw.pop("headers", {})}, **kw)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise StorageError(f"storage {method} {path} failed: {exc}") from exc
        return r

    def save(self, user_id: int, name: str, data: bytes) -> str:
        key = self._check_key(f"{user_id}/{uuid.uuid4().hex}-{name}")
        self._request("POST", f"/object/{self.bucket}/{key}", content=data,
                      headers={"x-upsert": "false", "content-type": "application/octet-stream"})
        return key

    def load(self, key: str) -> bytes:
        return self._request("GET", f"/object/{self.bucket}/{self._check_key(key)}").content

    def delete_user(self, user_id: int) -> None:
        prefix = f"{user_id}/"
        keys: list[str] = []
        offset = 0
        while True:
            page = self._request("POST", f"/object/list/{self.bucket}", json={
                "prefix": prefix, "limit": self.PAGE, "offset": offset, "sortBy": {"column": "name", "order": "asc"},
            }).json()
            # Names come back relative to the prefix; entries without an id are folders (none in our layout).
            keys += [f"{prefix}{item['name']}" for item in page if item.get("id") is not None]
            if len(page) < self.PAGE:
                break
            offset += self.PAGE
        for i in range(0, len(keys), self.PAGE):
            self._request("DELETE", f"/object/{self.bucket}", json={"prefixes": keys[i:i + self.PAGE]})


def storage_from_env() -> Storage:
    """Supabase Storage when SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY are set, else local disk."""
    return SupabaseStorage.from_env() or LocalStorage()


# --------------------------------------------------------------- extraction
def extract_text(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ResumeError(f"unsupported file type {ext or '(none)'}; allowed: {', '.join(ALLOWED_EXTENSIONS)}", 415)
    if len(data) > MAX_BYTES:
        raise ResumeError("file too large (max 2MB)", 413)
    if not data:
        raise ResumeError("empty file")
    try:
        if ext == ".pdf":
            from pypdf import PdfReader

            text = "\n".join((page.extract_text() or "") for page in PdfReader(io.BytesIO(data)).pages)
        elif ext == ".docx":
            from docx import Document

            text = "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
        else:
            text = data.decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 — any parser failure is "unreadable file"
        raise ResumeError(f"could not read {ext} file: {exc}") from exc
    text = re.sub(r"\n{3,}", "\n\n", text.replace("\x00", "")).strip()
    if len(text) < 20:
        raise ResumeError("no readable text found in file")
    return text


def store_resume(session: Session, user_id: int, filename: str, data: bytes, storage: Storage) -> ResumeVersion:
    """Persist a validated upload and make it the user's active resume. Re-uploading
    identical content reuses the existing version (so tailor cache keys stay stable)."""
    text = extract_text(filename, data)
    content_hash = hashlib.sha256(text.encode()).hexdigest()
    session.execute(update(ResumeVersion).where(ResumeVersion.user_id == user_id).values(is_active=False))
    existing = session.scalar(
        select(ResumeVersion).where(ResumeVersion.user_id == user_id, ResumeVersion.content_hash == content_hash)
    )
    if existing:
        existing.is_active = True
        session.flush()
        return existing
    ext = Path(filename).suffix.lower()
    key = storage.save(user_id, f"{content_hash[:16]}{ext}", data)  # server-chosen name: no path traversal
    row = ResumeVersion(
        user_id=user_id, filename=Path(filename).name[:255], storage_key=key, text=text,
        content_hash=content_hash, is_active=True,
    )
    session.add(row)
    session.flush()
    return row


# ------------------------------------------------------------------ parsing
class ParsedAchievement(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    summary: str = ""
    role_families: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    system_patterns: list[str] = Field(default_factory=list)
    seniority_signals: list[str] = Field(default_factory=list)
    business_signals: list[str] = Field(default_factory=list)
    leadership_signals: list[str] = Field(default_factory=list)


class ParsedResume(BaseModel):
    achievements: list[ParsedAchievement]


def _validate(raw: dict) -> None:
    ParsedResume(**raw)


def achievement_hash(title: str, summary: str) -> str:
    norm = " ".join(f"{title} {summary}".lower().split())
    return hashlib.sha256(norm.encode()).hexdigest()


def parse_resume(session: Session, user_id: int, resume: ResumeVersion, provider: LLMProvider) -> list[Achievement]:
    """Extract achievements and add the new ones; returns the user's full bank.

    Quota is consumed before the model call (fail closed). Dedupe key lives in
    `fields["content_hash"]` and is NOT recomputed when a user edits a row, so a
    re-parse can neither duplicate nor overwrite an edited achievement."""
    if resume.user_id != user_id:
        raise LookupError("resume not found")
    quota.consume(session, user_id, "resume_parse")
    routing = load_models()["routing"]["parse_resume"]
    prompt = PROMPT_PATH.read_text(encoding="utf-8").format(resume_text=resume.text[:MAX_TEXT_CHARS_TO_LLM])
    raw = provider._chat(  # noqa: SLF001 — same single call-site pattern as the classifier
        model=routing["model"],
        messages=[{"role": "user", "content": prompt}],
        max_tokens=routing["max_output_tokens"],
        temperature=routing["temperature"],
        workflow="parse_resume",
        job_id=str(resume.id),
        prompt_version=PROMPT_VERSION,
        validate=_validate,
    )
    parsed = ParsedResume(**raw)
    existing = {a.fields.get("content_hash"): a for a in list_achievements(session, user_id)}
    for item in parsed.achievements[:MAX_ACHIEVEMENTS]:
        h = achievement_hash(item.title, item.summary)
        if h in existing:
            if not existing[h].user_edited:
                existing[h].resume_id = resume.id
            continue
        fields = {k: [s.strip() for s in getattr(item, k) if s.strip()] for k in TAG_FIELDS}
        fields["content_hash"] = h
        row = Achievement(user_id=user_id, resume_id=resume.id, title=item.title.strip(), summary=item.summary.strip(), fields=fields)
        session.add(row)
        existing[h] = row
    session.flush()
    return list_achievements(session, user_id)


def list_achievements(session: Session, user_id: int) -> list[Achievement]:
    return list(session.scalars(select(Achievement).where(Achievement.user_id == user_id).order_by(Achievement.id)))


def active_resume(session: Session, user_id: int) -> ResumeVersion | None:
    return session.scalar(
        select(ResumeVersion).where(ResumeVersion.user_id == user_id, ResumeVersion.is_active.is_(True))
        .order_by(ResumeVersion.id.desc())
    )
