"""initial schema + append-only audit_log

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-22
"""
from alembic import op

from app.db.models import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

# Postgres: make audit_log INSERT-only at the DB layer (defense in depth — even a
# compromised app credential cannot rewrite history). No-op on other dialects.
_AUDIT_IMMUTABLE = """
CREATE OR REPLACE FUNCTION afm_audit_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_no_mutate
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION afm_audit_immutable();
"""


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    if bind.dialect.name == "postgresql":
        op.execute(_AUDIT_IMMUTABLE)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_log_no_mutate ON audit_log;")
        op.execute("DROP FUNCTION IF EXISTS afm_audit_immutable();")
    Base.metadata.drop_all(bind=bind)
