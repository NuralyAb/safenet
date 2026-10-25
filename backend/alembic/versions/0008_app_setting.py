"""Runtime app settings (key→value) — UI-configurable monitoring schedule.

Revision ID: 0008_app_setting
Revises: 0007_content_text
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_app_setting"
down_revision = "0007_content_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_setting",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("app_setting")
