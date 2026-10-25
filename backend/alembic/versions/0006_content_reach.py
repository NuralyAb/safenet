"""add reach metrics + triage priority to content_risk

Revision ID: 0006_content_reach
Revises: 0005_content_risk
Create Date: 2026-06-23
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0006_content_reach"
down_revision = "0005_content_risk"
branch_labels = None
depends_on = None

_COLS = {
    "views": sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
    "likes": sa.Column("likes", sa.Integer(), nullable=False, server_default="0"),
    "comments": sa.Column("comments", sa.Integer(), nullable=False, server_default="0"),
    "shares": sa.Column("shares", sa.Integer(), nullable=False, server_default="0"),
    "priority": sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
}


def _existing() -> set[str]:
    return {c["name"] for c in inspect(op.get_bind()).get_columns("content_risk")}


def upgrade() -> None:
    existing = _existing()
    for name, col in _COLS.items():
        if name not in existing:
            op.add_column("content_risk", col)
    if "priority" not in existing:
        op.create_index("ix_content_risk_priority", "content_risk", ["priority"])


def downgrade() -> None:
    existing = _existing()
    if "priority" in existing:
        op.drop_index("ix_content_risk_priority", table_name="content_risk")
    for name in _COLS:
        if name in existing:
            op.drop_column("content_risk", name)
