from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from jobai.product.api.deps import get_provider_factory, get_session
from jobai.product.api.schemas import AcceptIn
from jobai.product.db.models import Job, TailorRun, User
from jobai.product.services import ratelimit
from jobai.product.services import tailor as tailor_svc
from jobai.product.services.auth import get_current_user
from jobai.product.services.resume import active_resume

router = APIRouter()
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def run_out(run: TailorRun) -> dict:
    return {"run_id": run.id, "job_id": run.job_id, "resume_id": run.resume_id, "status": run.status,
            "bullets": run.proposal.get("bullets", []), "dropped": len(run.proposal.get("dropped", [])),
            "accepted": (run.accepted or {}).get("bullets")}


@router.post("/jobs/{job_id}/tailor", dependencies=[Depends(ratelimit.limit_by_user("tailor"))])
def propose(job_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session),
            provider_factory=Depends(get_provider_factory)) -> dict:
    if session.get(Job, job_id) is None:
        raise HTTPException(404, "job not found")
    resume = active_resume(session, user.id)
    if resume is None:
        raise HTTPException(400, "upload a resume first")
    provider = provider_factory(user.id, f"tailor-{uuid.uuid4().hex[:12]}")
    try:
        return run_out(tailor_svc.propose_tailor(session, user.id, job_id, resume.id, provider))
    except ValueError as exc:  # e.g. empty evidence bank
        raise HTTPException(400, str(exc)) from None


@router.post("/tailor/{run_id}/accept")
def accept(run_id: int, body: AcceptIn, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    try:
        return run_out(tailor_svc.accept_tailor(session, user.id, run_id, body.indices))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/tailor/{run_id}/download")
def download(run_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> Response:
    run = tailor_svc.get_run(session, user.id, run_id)
    try:
        data = tailor_svc.render_docx(run)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return Response(data, media_type=DOCX, headers={"Content-Disposition": f'attachment; filename="tailored-{run_id}.docx"'})
