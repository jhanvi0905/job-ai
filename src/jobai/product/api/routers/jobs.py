from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobai.product.api.deps import get_provider_factory, get_session
from jobai.product.db.models import Job, User, UserJobEvaluation
from jobai.product.services.auth import get_current_user

router = APIRouter()


def _job(session: Session, job_id: int) -> Job:
    job = session.get(Job, job_id)  # catalog is shared/readable
    if job is None:
        raise HTTPException(404, "job not found")
    return job


def _evaluation(session: Session, user_id: int, job_id: int) -> UserJobEvaluation | None:
    return session.scalar(select(UserJobEvaluation).where(
        UserJobEvaluation.user_id == user_id, UserJobEvaluation.job_id == job_id))


def job_detail(job: Job, ev: UserJobEvaluation | None) -> dict:
    cls = (ev.classification if ev else None) or {}
    match = (ev.match if ev else None) or {}
    return {
        "job": {"id": job.id, "company": job.company, "title": job.title, "location": job.location,
                "workplace_type": job.workplace_type, "apply_url": job.apply_url, "posted_at": job.posted_at,
                "description": job.description},
        "evaluation": None if ev is None else {
            "disposition": ev.disposition, "reason_code": ev.reason_code, "fit": ev.fit,
            "requirements": cls.get("key_requirements", []),
            "matched_achievements": match.get("matched_achievements", []),
            "strong_evidence": match.get("strong_evidence", []),
            "partial_evidence": match.get("partial_evidence", []),
            "gaps": match.get("gaps", []),
            "reason": match.get("reason") or cls.get("why"),
            "recommended_action": match.get("recommended_action"),
        },
    }


@router.get("/jobs/{job_id}")
def get_job(job_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    return job_detail(_job(session, job_id), _evaluation(session, user.id, job_id))


@router.post("/jobs/{job_id}/analyse")
def analyse(job_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session),
            provider_factory=Depends(get_provider_factory)) -> dict:
    """On-demand deep match (quota for it is enforced by the evaluation service)."""
    from jobai.product.services.evaluation import deep_match_job  # owned by the evaluation module

    job = _job(session, job_id)
    ev = deep_match_job(session, user.id, job_id, provider_factory(user.id, f"deep-{uuid.uuid4().hex[:12]}"))
    return job_detail(job, ev)
