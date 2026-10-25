"""add content_risk table (per-video explainable score)

Revision ID: 0005_content_risk
Revises: 0004_risk_disposition
Create Date: 2026-06-23
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0005_content_risk"
down_revision = "0004_risk_disposition"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table("content_risk"):
        return
    op.create_table(
        "content_risk",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_id", sa.String(64), nullable=False),
        sa.Column("author", sa.String(256), nullable=False, server_default=""),
        sa.Column("source", sa.String(32), nullable=False, server_default=""),
        sa.Column("url", sa.Text(), nullable=False, server_default=""),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("threat_level", sa.String(16), nullable=False),
        sa.Column("breakdown", sa.JSON(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("disposition", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("disposition_by", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_content_risk_content_id", "content_risk", ["content_id"], unique=True)
    op.create_index("ix_content_risk_author", "content_risk", ["author"])
    op.create_index("ix_content_risk_source", "content_risk", ["source"])
    op.create_index("ix_content_risk_score", "content_risk", ["score"])
    op.create_index("ix_content_risk_disposition", "content_risk", ["disposition"])


def downgrade() -> None:
    if _has_table("content_risk"):
        op.drop_table("content_risk")
