"""add watch_target (continuous monitoring watchlist)

Revision ID: 0003_watch_target
Revises: 0002_content_claims
Create Date: 2026-06-23
"""
from alembic import op

from app.db.models import WatchTarget

revision = "0003_watch_target"
down_revision = "0002_content_claims"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # checkfirst -> idempotent: 0001's create_all may already include it on a fresh DB.
    WatchTarget.__table__.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    WatchTarget.__table__.drop(bind=op.get_bind(), checkfirst=True)
