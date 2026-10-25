"""add NLP claim flags to content

Revision ID: 0002_content_claims
Revises: 0001_initial
Create Date: 2026-06-23
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0002_content_claims"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

_COLS = ["promises_returns", "has_referral", "has_license", "gambling_content"]


def _existing() -> set[str]:
    return {c["name"] for c in inspect(op.get_bind()).get_columns("content")}


def upgrade() -> None:
    # Idempotent: 0001's create_all may already include these on a fresh DB; only
    # add what's missing (older DBs created before the columns existed).
    existing = _existing()
    for col in _COLS:
        if col not in existing:
            op.add_column("content", sa.Column(col, sa.Boolean(), nullable=False,
                                                server_default=sa.false()))


def downgrade() -> None:
    existing = _existing()
    for col in _COLS:
        if col in existing:
            op.drop_column("content", col)
