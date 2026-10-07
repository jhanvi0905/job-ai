"""Request-scoped dependencies shared by routers and `services.auth`.

Kept free of any import from `services` so auth can depend on it without a cycle."""
from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session


def get_session(request: Request) -> Iterator[Session]:
    """One session per request: commit on success, roll back on any exception
    (so a quota debit never survives a failed LLM call)."""
    session: Session = request.app.state.session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_storage(request: Request):
    return request.app.state.storage


def get_provider_factory(request: Request):
    """Returns `(user_id, run_id) -> LLMProvider`. Overridable via
    `app.state.provider_factory` (tests inject fakes; no network)."""
    factory = getattr(request.app.state, "provider_factory", None)
    if factory is not None:
        return factory

    def default(user_id: int, run_id: str):
        from jobai.product.services.llm import make_user_provider  # lazy: owned by another module

        return make_user_provider(request.app.state.session_factory, user_id, run_id)

    return default
