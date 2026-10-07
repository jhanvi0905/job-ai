"""Payment webhook stub. See services.billing for the PaymentProvider port."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from jobai.product.api.deps import get_session
from jobai.product.db.models import User
from jobai.product.services import billing as billing_svc

router = APIRouter()


@router.post("/billing/webhook", status_code=204)
async def webhook(request: Request, session: Session = Depends(get_session)):
    provider = getattr(request.app.state, "payment_provider", None) or billing_svc.HmacPaymentProvider()
    try:
        event = provider.parse_event(request.headers, await request.body())
    except billing_svc.WebhookError as exc:
        raise HTTPException(400, str(exc)) from None
    if session.get(User, event.user_id) is None:
        raise HTTPException(404, "unknown user")
    billing_svc.grant(session, event.user_id, event.credits, reason="purchase", ref=event.event_id)  # idempotent
    return Response(status_code=204)
