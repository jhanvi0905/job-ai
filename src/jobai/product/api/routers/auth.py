"""The account (`/me`) endpoints, including erasure.

There are no signup/login routes: the browser authenticates with Supabase Auth
and sends its access token; `get_current_user` provisions our row on first use."""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete
from sqlalchemy.orm import Session

from jobai.product.api.deps import get_session, get_storage
from jobai.product.api.schemas import UserOut
from jobai.product.db.models import Base, ErasedAccount, User, WaitlistEntry
from jobai.product.services import auth as auth_svc

log = logging.getLogger(__name__)
router = APIRouter()

# Tables that don't hang off a user_id column.
_NOT_OWNED = {"users", "jobs", "waitlist", "erased_accounts"}


def _user_out(u: User) -> UserOut:
    return UserOut(id=u.id, email=u.email, plan=u.plan, created_at=u.created_at)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(auth_svc.get_current_user)):
    return _user_out(user)


@router.delete("/me", status_code=204)
def erase_me(request: Request, user: User = Depends(auth_svc.get_current_user),
             session: Session = Depends(get_session), storage=Depends(get_storage)):
    """Hard erasure: every owned row (explicit, since SQLite doesn't enforce FK
    cascades by default), the user, their waitlist entry, uploaded files, and
    finally the Supabase auth user. If the Supabase call fails the request
    returns 502 and the DB transaction rolls back, so a retry redoes everything."""
    user_id, auth_id = user.id, user.auth_id
    for table in Base.metadata.sorted_tables:
        if table.name not in _NOT_OWNED and "user_id" in table.c:
            session.execute(delete(table).where(table.c.user_id == user_id))
    session.execute(delete(WaitlistEntry).where(WaitlistEntry.email == user.email))
    session.delete(user)
    if auth_id is not None:
        session.add(ErasedAccount(auth_id=auth_id))  # outstanding access tokens can't re-provision
    session.flush()
    storage.delete_user(user_id)

    admin: auth_svc.SupabaseAdmin | None = getattr(request.app.state, "auth_admin", None)
    if auth_id is None:
        log.info("user %s has no Supabase identity; nothing to delete in Supabase Auth", user_id)
    elif admin is None:
        log.info("SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY unset; skipped deleting Supabase auth user for user %s", user_id)
    else:
        try:
            admin.delete_user(auth_id)
        except httpx.HTTPError as exc:
            log.error("Supabase admin delete failed for user %s: %s", user_id, exc)
            raise HTTPException(502, "could not complete account deletion; please retry") from None
    return Response(status_code=204)
