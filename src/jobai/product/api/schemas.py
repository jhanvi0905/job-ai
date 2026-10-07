"""Request/response models for the product API."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: int
    email: str
    plan: str
    created_at: datetime


class WaitlistIn(BaseModel):
    email: str = Field(max_length=320)
    source: str | None = Field(default=None, max_length=64)


class ResumeOut(BaseModel):
    id: int
    filename: str
    is_active: bool
    created_at: datetime
    chars: int


class AchievementOut(BaseModel):
    id: int
    resume_id: int | None
    title: str
    summary: str
    fields: dict
    user_edited: bool


class AchievementPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    summary: str | None = None
    fields: dict | None = None


class ResumeUploadOut(BaseModel):
    resume: ResumeOut
    task_id: str  # the queued resume_parse task; poll GET /tasks/{task_id}


class AcceptIn(BaseModel):
    indices: list[int]


class ApplicationIn(BaseModel):
    status: Literal["saved", "tailored", "applied", "interview", "offer", "rejected"]
    notes: str = ""
    applied_on: date | None = None


class ApplicationOut(BaseModel):
    job_id: int
    status: str
    notes: str
    applied_on: date | None
    updated_at: datetime
    company: str | None = None
    title: str | None = None
