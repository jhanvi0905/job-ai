from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobai.product.api.deps import get_session
from jobai.product.api.schemas import ApplicationIn, ApplicationOut
from jobai.product.db.models import Application, Job, User
from jobai.product.services.auth import get_current_user

router = APIRouter()


def _out(app: Application, job: Job | None) -> ApplicationOut:
    return ApplicationOut(job_id=app.job_id, status=app.status, notes=app.notes, applied_on=app.applied_on,
                          updated_at=app.updated_at, company=job.company if job else None, title=job.title if job else None)


@router.get("/applications", response_model=list[ApplicationOut])
def list_applications(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    rows = session.execute(select(Application, Job).join(Job, Job.id == Application.job_id)
                           .where(Application.user_id == user.id).order_by(Application.updated_at.desc())).all()
    return [_out(a, j) for a, j in rows]


@router.put("/applications/{job_id}", response_model=ApplicationOut)
def upsert_application(job_id: int, body: ApplicationIn, user: User = Depends(get_current_user),
                       session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    app = session.scalar(select(Application).where(Application.user_id == user.id, Application.job_id == job_id))
    if app is None:
        app = Application(user_id=user.id, job_id=job_id)
        session.add(app)
    app.status, app.notes, app.applied_on = body.status, body.notes, body.applied_on
    session.flush()
    session.refresh(app)
    return _out(app, job)
