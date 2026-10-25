"""Per-target monitoring schedule (interval + video limit).

Each watch target can run on its own cadence (e.g. one Instagram once a day,
another twice a day) instead of a single global interval.

Revision ID: 0009_watch_target_schedule
Revises: 0008_app_setting
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_watch_target_schedule"
down_revision = "0008_app_setting"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("watch_target", sa.Column("interval_seconds", sa.Integer(), nullable=True))
    op.add_column("watch_target", sa.Column("video_limit", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("watch_target", "video_limit")
    op.drop_column("watch_target", "interval_seconds")
