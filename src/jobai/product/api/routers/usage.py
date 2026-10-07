from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from jobai.product.api.deps import get_session
from jobai.product.db.models import User
from jobai.product.services import billing, quota
from jobai.product.services.auth import get_current_user

router = APIRouter()


@router.get("/usage")
def usage(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    return {
        "plan": user.plan,
        "limits": dict(quota.PLAN_LIMITS[user.plan]),
        "used": {k: quota.used_today(session, user.id, k) for k in quota.KINDS},
        "credits": billing.balance(session, user.id),
    }
