"""SafeNet KZ: track + language on content_risk, original post text on content.

`content_risk.track` (lottery | casino | pyramid | "") lets the analyst filter the
review queue by scheme type; `content.caption` keeps the original post / message
text next to the speech transcript and OCR (evidence for the quotes in the breakdown).

Revision ID: 0013_safenet_track
Revises: 0012_notification_reason
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_safenet_track"
down_revision = "0012_notification_reason"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("content_risk", sa.Column("track", sa.String(length=16), nullable=False, server_default=""))
    op.add_column("content_risk", sa.Column("lang", sa.String(length=16), nullable=False, server_default=""))
    op.create_index("ix_content_risk_track", "content_risk", ["track"])
    op.add_column("content", sa.Column("caption", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("content", "caption")
    op.drop_index("ix_content_risk_track", table_name="content_risk")
    op.drop_column("content_risk", "lang")
    op.drop_column("content_risk", "track")
