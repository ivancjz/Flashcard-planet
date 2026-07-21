"""add daily market report snapshots

Revision ID: 0041
Revises: 0040
Create Date: 2026-07-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_market_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="published"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("market_sentiment", sa.String(32), nullable=False),
        sa.Column("confidence_label", sa.String(32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("overview_json", JSONB, nullable=False),
        sa.Column("evidence_json", JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_date", name="uq_daily_market_reports_report_date"),
    )
    op.create_index(
        "ix_daily_market_reports_report_date",
        "daily_market_reports",
        ["report_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_daily_market_reports_report_date", table_name="daily_market_reports")
    op.drop_table("daily_market_reports")
