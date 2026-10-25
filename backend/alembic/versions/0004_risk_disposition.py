"""add triage disposition to risk_assessment

Revision ID: 0004_risk_disposition
Revises: 0003_watch_target
Create Date: 2026-06-23
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0004_risk_disposition"
down_revision = "0003_watch_target"
branch_labels = None
depends_on = None

_COLS = {
    "disposition": sa.Column("disposition", sa.String(16), nullable=False, server_default="pending"),
    "disposition_by": sa.Column("disposition_by", sa.String(128), nullable=True),
    "updated_at": sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
}


def _existing() -> set[str]:
    return {c["name"] for c in inspect(op.get_bind()).get_columns("risk_assessment")}


def upgrade() -> None:
    existing = _existing()
    for name, col in _COLS.items():
        if name not in existing:
            op.add_column("risk_assessment", col)


def downgrade() -> None:
    existing = _existing()
    for name in _COLS:
        if name in existing:
            op.drop_column("risk_assessment", name)
