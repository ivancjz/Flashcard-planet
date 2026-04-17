"""Add access_tier to users.

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-11 00:00:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "access_tier",
            sa.String(16),
            nullable=False,
            server_default="free",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "access_tier")
