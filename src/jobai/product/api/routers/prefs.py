from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from jobai.product.api.deps import get_session
from jobai.product.db.models import SearchPrefs, User
from jobai.product.services.auth import get_current_user

router = APIRouter()


def _model():
    from jobai.product.services.prefs import SearchPrefsModel  # owned by the prefs module

    return SearchPrefsModel


@router.get("/prefs")
def get_prefs(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    row = session.get(SearchPrefs, user.id)
    return _model()(**(row.data if row else {})).model_dump(mode="json")


@router.put("/prefs")
def put_prefs(body: dict, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    # Validated through the model (422 on bad input); we store the normalised dump.
    prefs = _model()(**body).model_dump(mode="json")
    row = session.get(SearchPrefs, user.id)
    if row is None:
        session.add(SearchPrefs(user_id=user.id, data=prefs))
    else:
        row.data = prefs
    return prefs
