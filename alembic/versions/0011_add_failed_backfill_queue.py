"""
alembic/versions/0011_add_failed_backfill_queue.py

Independent retry queue for backfill pass failures.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "failed_backfill_queue",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "asset_id",
            UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("failure_type", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "last_attempted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("is_permanent", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_fbq_asset_id", "failed_backfill_queue", ["asset_id"])
    op.create_index(
        "ix_fbq_permanent_attempted",
        "failed_backfill_queue",
        ["is_permanent", "last_attempted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_fbq_permanent_attempted", table_name="failed_backfill_queue")
    op.drop_index("ix_fbq_asset_id", table_name="failed_backfill_queue")
    op.drop_table("failed_backfill_queue")
