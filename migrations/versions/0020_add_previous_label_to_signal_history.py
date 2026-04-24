"""add previous_label column to asset_signal_history

Revision ID: 0020
Revises: 0019
Create Date: 2026-04-24

Stores the previous signal label at write time, eliminating the need for
LAG() window functions or LATERAL lookups in the /alerts endpoint.
Previous rows remain NULL (no backfill — old transitions not needed).
"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "asset_signal_history",
        sa.Column("previous_label", sa.String(32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("asset_signal_history", "previous_label")
