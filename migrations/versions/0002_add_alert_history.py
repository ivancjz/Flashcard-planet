"""Add alert_history table

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-08 00:00:01.000000+00:00

Creates the alert_history table which records each alert trigger event as an
immutable audit log. Foreign keys to alerts and assets use SET NULL / CASCADE
respectively so history rows survive parent deletions.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alert_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_type", sa.String(64), nullable=False),
        sa.Column("asset_name", sa.String(255), nullable=False),
        sa.Column("triggered_at", sa.DateTime(), nullable=False),
        sa.Column("price_at_trigger", sa.Numeric(12, 2), nullable=True),
        sa.Column("reference_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("percent_change", sa.Numeric(8, 2), nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("notification_content", sa.Text(), nullable=True),
        sa.Column("delivery_status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alert_history_alert_id", "alert_history", ["alert_id"])
    op.create_index("ix_alert_history_user_id", "alert_history", ["user_id"])
    op.create_index("ix_alert_history_asset_id", "alert_history", ["asset_id"])
    op.create_index("ix_alert_history_triggered_at", "alert_history", ["triggered_at"])


def downgrade() -> None:
    op.drop_table("alert_history")
