"""add daily report intelligence persistence

Revision ID: 0043
Revises: 0042
Create Date: 2026-07-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_report_intelligence",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "report_id",
            UUID(as_uuid=True),
            sa.ForeignKey("daily_market_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("headline", sa.Text(), nullable=True),
        sa.Column("commentary", sa.Text(), nullable=True),
        sa.Column("risk_summary", sa.Text(), nullable=True),
        sa.Column(
            "key_observations_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "evidence_refs_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("provider", sa.String(32), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint(
            "report_id",
            "evidence_hash",
            "prompt_version",
            name="uq_daily_report_intelligence_cache_key",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'published', 'insufficient_evidence', 'failed')",
            name="ck_daily_report_intelligence_status",
        ),
        sa.CheckConstraint(
            "attempt_count BETWEEN 0 AND 3",
            name="ck_daily_report_intelligence_attempt_count",
        ),
    )
    op.create_index(
        "ix_daily_report_intelligence_report_id",
        "daily_report_intelligence",
        ["report_id"],
    )
    op.create_index(
        "ix_daily_report_intelligence_status_updated",
        "daily_report_intelligence",
        ["status", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_daily_report_intelligence_status_updated",
        table_name="daily_report_intelligence",
    )
    op.drop_index(
        "ix_daily_report_intelligence_report_id",
        table_name="daily_report_intelligence",
    )
    op.drop_table("daily_report_intelligence")
