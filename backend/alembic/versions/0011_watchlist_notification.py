"""Watchlist notifications — 'new video for a monitored account' events.

Surfaced as toasts so an analyst is alerted when an account under continuous
monitoring publishes new content (which the sweep also auto-analyses).

Revision ID: 0011_watchlist_notification
Revises: 0010_licensed_entity
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_watchlist_notification"
down_revision = "0010_licensed_entity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlist_notification",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_id", sa.String(length=64), nullable=False),
        sa.Column("author", sa.String(length=256), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("url", sa.Text(), nullable=False, server_default=""),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("threat_level", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_watchlist_notification_content_id", "watchlist_notification",
                    ["content_id"], unique=True)
    op.create_index("ix_watchlist_notification_author", "watchlist_notification", ["author"])
    op.create_index("ix_watchlist_notification_created_at", "watchlist_notification", ["created_at"])
    op.create_index("ix_watchlist_notification_read_at", "watchlist_notification", ["read_at"])


def downgrade() -> None:
    for ix in ("read_at", "created_at", "author", "content_id"):
        op.drop_index(f"ix_watchlist_notification_{ix}", table_name="watchlist_notification")
    op.drop_table("watchlist_notification")
