"""Add resolution_type to human_review_queue.

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-11 00:00:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "human_review_queue",
        sa.Column("resolution_type", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("human_review_queue", "resolution_type")
