"""Add explanation columns to asset_signals.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-10 00:00:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("asset_signals", sa.Column("explanation", sa.Text(), nullable=True))
    op.add_column(
        "asset_signals",
        sa.Column("explained_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("asset_signals", "explained_at")
    op.drop_column("asset_signals", "explanation")
