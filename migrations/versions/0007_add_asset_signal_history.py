"""Add asset_signal_history table.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-11 00:00:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "asset_signal_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("label", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("price_delta_pct", sa.Numeric(8, 2), nullable=True),
        sa.Column("liquidity_score", sa.Integer(), nullable=True),
        sa.Column("prediction", sa.String(32), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_asset_signal_history_asset_computed",
        "asset_signal_history",
        ["asset_id", "computed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_asset_signal_history_asset_computed", table_name="asset_signal_history")
    op.drop_table("asset_signal_history")
