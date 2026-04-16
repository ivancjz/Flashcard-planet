"""Add upgrade_requests table.

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-16 00:00:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "upgrade_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("admin_note", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_upgrade_requests_user_id", "upgrade_requests", ["user_id"])
    op.create_index(
        "ix_upgrade_requests_user_status",
        "upgrade_requests",
        ["user_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_upgrade_requests_user_status", table_name="upgrade_requests")
    op.drop_index("ix_upgrade_requests_user_id", table_name="upgrade_requests")
    op.drop_table("upgrade_requests")
