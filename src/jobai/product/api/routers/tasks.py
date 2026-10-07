"""Background task status (feed refresh, resume parse). Owner only."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from jobai.product.api.deps import get_session
from jobai.product.db.models import User
from jobai.product.services import tasks as tasks_svc
from jobai.product.services.auth import get_current_user

router = APIRouter()


@router.get("/tasks/{task_id}")
def get_task(task_id: str, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    """`{"id","kind","status","result","error","created_at","finished_at"}`. 404 for
    unknown ids, malformed ids and other users' tasks alike (no enumeration)."""
    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(404, "task not found") from None
    task = tasks_svc.get_for_user(session, tid, user.id)
    if task is None:
        raise HTTPException(404, "task not found")
    return tasks_svc.to_dict(task)
