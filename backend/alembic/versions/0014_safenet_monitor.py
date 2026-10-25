"""SafeNet KZ scheme monitor: polled sources + the live feed of checked posts.

`monitor_source` — channels / accounts the monitor polls (connector telegram_web | demo).
`monitor_event` — every post it checked; (source_id, external_id) is unique so a post
is never checked twice. Flagged posts also land in content_risk (the review queue).

Revision ID: 0014_safenet_monitor
Revises: 0013_safenet_track
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_safenet_monitor"
down_revision = "0013_safenet_track"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monitor_source",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("handle", sa.String(length=256), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("connector", sa.String(length=32), nullable=False, server_default="telegram_web"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("added_by", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_polled_ts", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cursor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scanned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("flagged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=256), nullable=False, server_default=""),
    )
    op.create_index("ix_monitor_source_platform", "monitor_source", ["platform"])
    op.create_table(
        "monitor_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("author", sa.String(length=256), nullable=False),
        sa.Column("url", sa.Text(), nullable=False, server_default=""),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("threat_level", sa.String(length=16), nullable=False, server_default="LOW"),
        sa.Column("track", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("lang", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("flagged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("signals", sa.JSON(), nullable=False),
        sa.Column("breakdown", sa.JSON(), nullable=False),
        sa.Column("content_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_ts", sa.Float(), nullable=False),
        sa.UniqueConstraint("source_id", "external_id", name="uq_monitor_event_post"),
    )
    op.create_index("ix_monitor_event_source_id", "monitor_event", ["source_id"])
    op.create_index("ix_monitor_event_flagged", "monitor_event", ["flagged"])
    op.create_index("ix_monitor_event_created_ts", "monitor_event", ["created_ts"])


def downgrade() -> None:
    op.drop_table("monitor_event")
    op.drop_table("monitor_source")
