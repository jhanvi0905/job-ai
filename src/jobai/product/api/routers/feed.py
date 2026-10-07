"""The user's ranked job feed. Only evaluations owned by the caller are joined."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jobai.product.api.deps import get_session
from jobai.product.db.models import Job, User, UserJobEvaluation
from jobai.product.services import ratelimit
from jobai.product.services import tasks as tasks_svc
from jobai.product.services.auth import get_current_user

router = APIRouter()

FIT_RANK = {"no": 0, "weak": 1, "plausible": 2, "strong": 3}
FEED_DISPOSITIONS = ("matched", "triaged", "deferred")


def feed_item(job: Job, ev: UserJobEvaluation) -> dict:
    match = ev.match or {}
    cls = ev.classification or {}
    return {
        "job_id": job.id, "company": job.company, "title": job.title, "location": job.location,
        "workplace_type": job.workplace_type, "apply_url": job.apply_url, "posted_at": job.posted_at,
        "fit": ev.fit, "disposition": ev.disposition,
        "why_fits": match.get("reason") or cls.get("why"),
        "gaps": list(match.get("gaps") or []),
    }


@router.get("/feed")
def feed(min_fit: str | None = Query(None, pattern="^(no|weak|plausible|strong)$"),
         limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
         user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    where = [UserJobEvaluation.user_id == user.id, UserJobEvaluation.disposition.in_(FEED_DISPOSITIONS)]
    if min_fit:
        where.append(UserJobEvaluation.fit_rank >= FIT_RANK[min_fit])
    total = session.scalar(select(func.count()).select_from(UserJobEvaluation).where(*where)) or 0
    rows = session.execute(
        select(Job, UserJobEvaluation).join(UserJobEvaluation, UserJobEvaluation.job_id == Job.id).where(*where)
        .order_by(UserJobEvaluation.fit_rank.desc(), Job.posted_at.desc(), Job.id.desc()).limit(limit).offset(offset)
    ).all()
    return {"items": [feed_item(j, e) for j, e in rows], "total": total}


@router.post("/feed/refresh", status_code=202, dependencies=[Depends(ratelimit.limit_by_user("feed_refresh"))])
def refresh(max_jobs: int | None = Query(None, ge=1, le=500), user: User = Depends(get_current_user),
            session: Session = Depends(get_session)) -> dict:
    """Queue a feed refresh for the worker (it makes many LLM calls; never run in
    the request). Returns 202 with the task to poll at GET /tasks/{task_id}. If one
    is already queued or running for this user, that task is returned instead.
    Per-plan caps are enforced by evaluate_for_user inside the worker."""
    payload = {"max_jobs": max_jobs} if max_jobs is not None else {}
    task, _created = tasks_svc.enqueue(session, "feed_refresh", user_id=user.id, payload=payload)
    return {"task_id": str(task.id), "status": task.status}
