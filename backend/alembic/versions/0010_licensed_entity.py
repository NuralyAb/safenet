"""Licensed-operator registry (imported from АРРФР / egov).

Maps a content identifier (domain / @handle) to a license + status, so the
license check verifies against real regulator data instead of an env allowlist.

Revision ID: 0010_licensed_entity
Revises: 0009_watch_target_schedule
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_licensed_entity"
down_revision = "0009_watch_target_schedule"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "licensed_entity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("identifier", sa.String(length=256), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="domain"),
        sa.Column("operator", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("bin", sa.String(length=32), nullable=True),
        sa.Column("license_no", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("imported_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_licensed_entity_identifier", "licensed_entity", ["identifier"], unique=True)
    op.create_index("ix_licensed_entity_status", "licensed_entity", ["status"])


def downgrade() -> None:
    op.drop_index("ix_licensed_entity_status", table_name="licensed_entity")
    op.drop_index("ix_licensed_entity_identifier", table_name="licensed_entity")
    op.drop_table("licensed_entity")
