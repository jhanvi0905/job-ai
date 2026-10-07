"""Resume upload/parse and the evidence-bank (achievement) CRUD."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobai.product.api.deps import get_session, get_storage
from jobai.product.api.schemas import AchievementOut, AchievementPatch, ResumeOut, ResumeUploadOut
from jobai.product.db.models import Achievement, ResumeVersion, User
from jobai.product.services import quota
from jobai.product.services import resume as resume_svc
from jobai.product.services import tasks as tasks_svc
from jobai.product.services.auth import get_current_user

router = APIRouter()


def resume_out(r: ResumeVersion) -> ResumeOut:
    return ResumeOut(id=r.id, filename=r.filename, is_active=r.is_active, created_at=r.created_at, chars=len(r.text))


def ach_out(a: Achievement) -> AchievementOut:
    return AchievementOut(id=a.id, resume_id=a.resume_id, title=a.title, summary=a.summary,
                          fields={k: v for k, v in a.fields.items() if k != "content_hash"}, user_edited=a.user_edited)


def _own_achievement(session: Session, user_id: int, aid: int) -> Achievement:
    a = session.scalar(select(Achievement).where(Achievement.id == aid, Achievement.user_id == user_id))
    if a is None:
        raise HTTPException(404, "achievement not found")
    return a


@router.post("/resume", response_model=ResumeUploadOut, status_code=201)
async def upload_resume(file: UploadFile = File(...), user: User = Depends(get_current_user),
                        session: Session = Depends(get_session), storage=Depends(get_storage)):
    """Validate + store the file now; parsing (an LLM call) is queued for the worker.
    Poll GET /tasks/{task_id}; achievements appear once it succeeds. The parse quota
    is checked here (fail fast with 429) and consumed by the worker."""
    if quota.remaining(session, user.id, "resume_parse") - tasks_svc.active_count(session, user.id, "resume_parse") <= 0:
        raise quota.QuotaExceeded("resume_parse", quota.PLAN_LIMITS[user.plan]["resume_parse"])
    data = await file.read(resume_svc.MAX_BYTES + 1)  # bounded read: never buffer an oversized upload
    row = resume_svc.store_resume(session, user.id, file.filename or "resume.txt", data, storage)
    task, _ = tasks_svc.enqueue(session, "resume_parse", user_id=user.id, payload={"resume_id": row.id})
    return ResumeUploadOut(resume=resume_out(row), task_id=str(task.id))


@router.get("/resume", response_model=ResumeOut | None)
def get_resume(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    row = resume_svc.active_resume(session, user.id)
    return resume_out(row) if row else None


@router.get("/achievements", response_model=list[AchievementOut])
def list_achievements(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return [ach_out(a) for a in resume_svc.list_achievements(session, user.id)]


@router.patch("/achievements/{aid}", response_model=AchievementOut)
def patch_achievement(aid: int, body: AchievementPatch, user: User = Depends(get_current_user),
                      session: Session = Depends(get_session)):
    a = _own_achievement(session, user.id, aid)
    if body.title is not None:
        a.title = body.title
    if body.summary is not None:
        a.summary = body.summary
    if body.fields is not None:
        # Tags only; keep the dedupe hash so re-parsing can't resurrect the original.
        keep = {"content_hash": a.fields.get("content_hash")}
        a.fields = {**{k: v for k, v in body.fields.items() if k in resume_svc.TAG_FIELDS and isinstance(v, list)}, **keep}
    a.user_edited = True
    session.flush()
    return ach_out(a)


@router.delete("/achievements/{aid}", status_code=204)
def delete_achievement(aid: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    session.delete(_own_achievement(session, user.id, aid))
    return Response(status_code=204)
