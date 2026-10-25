"""Retain analysis text on content (transcript / OCR / tags).

Evidentiary requirement: the speech transcript and on-screen text extracted at
process time must be persisted so an analyst can re-read the clip's content later,
not just see the distilled claim flags.

Revision ID: 0007_content_text
Revises: 0006_content_reach
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_content_text"
down_revision = "0006_content_reach"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content", sa.Column("transcript", sa.Text(), nullable=True))
    op.add_column("content", sa.Column("ocr_text", sa.Text(), nullable=True))
    op.add_column("content", sa.Column("tags", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("content", "tags")
    op.drop_column("content", "ocr_text")
    op.drop_column("content", "transcript")
