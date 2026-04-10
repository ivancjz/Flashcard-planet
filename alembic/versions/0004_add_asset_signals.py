"""Add asset_signals table for signal detection.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-10 00:00:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "asset_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id"),
            nullable=False,
        ),
        sa.Column("label", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("price_delta_pct", sa.Numeric(8, 2), nullable=True),
        sa.Column("liquidity_score", sa.Integer(), nullable=True),
        sa.Column("prediction", sa.String(32), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_asset_signals_asset_id", "asset_signals", ["asset_id"], unique=True)
    op.create_index("ix_asset_signals_label", "asset_signals", ["label"])


def downgrade() -> None:
    op.drop_index("ix_asset_signals_label", table_name="asset_signals")
    op.drop_index("ix_asset_signals_asset_id", table_name="asset_signals")
    op.drop_table("asset_signals")
