"""Engine/session factory. SQLite for dev and tests, Postgres (Supabase) in
production — the only switch is DATABASE_URL.

Supabase's transaction pooler (Supavisor, port 6543, or any URL tagged
`?pgbouncer=true`) multiplexes server connections per transaction, which breaks
psycopg3's server-side prepared statements; for those URLs we disable them."""
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_URL = "sqlite:///data/product.db"


TRANSACTION_POOLER_PORT = 6543


def make_engine(url: str | None = None) -> Engine:
    url = url or os.environ.get("DATABASE_URL", DEFAULT_URL)
    if url.startswith("postgresql://"):  # force the psycopg3 driver
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    parsed = make_url(url)
    pooled = parsed.port == TRANSACTION_POOLER_PORT or str(parsed.query.get("pgbouncer", "")).lower() == "true"
    parsed = parsed.difference_update_query(["pgbouncer"])  # not a libpq option; psycopg would reject it
    connect_args = {"prepare_threshold": None} if pooled else {}
    return create_engine(parsed, pool_pre_ping=True, connect_args=connect_args)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
