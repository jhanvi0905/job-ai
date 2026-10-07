"""supabase: auth_id, erased_accounts, RLS deny-all, pgvector

Revision ID: 0002
Revises: 0001

* `users.auth_id` links a row to Supabase `auth.users.id` (JWT `sub`); the
  integer PK stays so no foreign key changes. `password_hash` becomes nullable
  (legacy, no longer written).
* `erased_accounts` tombstones erased identities (see models.ErasedAccount).
* Postgres only: RLS is enabled with NO policies on every table, so Supabase's
  auto-generated Data API (anon / authenticated roles) can read nothing. The
  API connects as the table owner / a BYPASSRLS role and enforces tenancy in
  code, so it is unaffected. `vector` is enabled for the later catalog prefilter.
"""
import sqlalchemy as sa
from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

# Every table that exists after this revision. Later migrations that create a
# table must declare their own RLS_TABLES (tests/product/test_supabase.py checks
# the union covers Base.metadata).
RLS_TABLES = (
    "alembic_version", "users", "search_prefs", "jobs", "user_job_evaluations", "resume_versions",
    "achievements", "tailor_runs", "applications", "llm_calls", "usage_counters", "credit_ledger",
    "waitlist", "erased_accounts",
)


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('auth_id', sa.Uuid(), nullable=True))
        batch_op.alter_column('password_hash', existing_type=sa.String(length=255), nullable=True)
        batch_op.create_index(batch_op.f('ix_users_auth_id'), ['auth_id'], unique=True)

    op.create_table('erased_accounts',
    sa.Column('auth_id', sa.Uuid(), nullable=False),
    sa.Column('erased_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('auth_id')
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        for table in RLS_TABLES:
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in RLS_TABLES:
            if table != "erased_accounts":
                op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
        # The `vector` extension is left installed: other objects may depend on it.

    op.drop_table('erased_accounts')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_auth_id'))
        # Fails if Supabase-provisioned users (null password_hash) exist; that is intended.
        batch_op.alter_column('password_hash', existing_type=sa.String(length=255), nullable=False)
        batch_op.drop_column('auth_id')
