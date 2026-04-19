"""add signal_context JSONB to asset_signals and asset_signal_history

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("asset_signals", sa.Column("signal_context", JSONB, nullable=True))
    op.add_column("asset_signal_history", sa.Column("signal_context", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("asset_signal_history", "signal_context")
    op.drop_column("asset_signals", "signal_context")
