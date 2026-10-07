"""Alembic env: URL from DIRECT_DATABASE_URL, else DATABASE_URL (same switch as
jobai.product.db.session). On Supabase, DATABASE_URL is usually the transaction
pooler (port 6543) used by the app; DDL should go over the direct/session
connection (port 5432), so set DIRECT_DATABASE_URL for migrations."""
import os

from alembic import context

from jobai.product.db.models import Base
from jobai.product.db.session import DEFAULT_URL, make_engine

target_metadata = Base.metadata


def _url() -> str:
    # An explicit sqlalchemy.url (set programmatically, e.g. by tests) wins over the env.
    return (context.config.get_main_option("sqlalchemy.url") or os.environ.get("DIRECT_DATABASE_URL")
            or os.environ.get("DATABASE_URL", DEFAULT_URL))


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
