"""Add `reason` to watchlist_notification (watched | high_risk).

Distinguishes a new-video alert from a monitored account from a proactive radar
hit (discovered content scoring above the alert threshold).

Revision ID: 0012_notification_reason
Revises: 0011_watchlist_notification
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_notification_reason"
down_revision = "0011_watchlist_notification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("watchlist_notification",
                  sa.Column("reason", sa.String(length=16), nullable=False, server_default="watched"))


def downgrade() -> None:
    op.drop_column("watchlist_notification", "reason")
