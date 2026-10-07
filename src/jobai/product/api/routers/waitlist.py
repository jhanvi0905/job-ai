from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobai.product.api.deps import get_session
from jobai.product.api.schemas import WaitlistIn
from jobai.product.db.models import WaitlistEntry
from jobai.product.services import ratelimit
from jobai.product.services.auth import normalize_email

router = APIRouter()


@router.post("/waitlist", status_code=204, dependencies=[Depends(ratelimit.limit_by_ip("waitlist"))])
def join(body: WaitlistIn, session: Session = Depends(get_session)):
    """Public and idempotent: re-submitting an email is a silent success (no enumeration)."""
    email = normalize_email(body.email)
    if "@" not in email:
        raise HTTPException(400, "invalid email")
    if not session.scalar(select(WaitlistEntry.id).where(WaitlistEntry.email == email)):
        session.add(WaitlistEntry(email=email, source=body.source))
    return Response(status_code=204)
