"""add catalyst engine persistence fields

Revision ID: 0042
Revises: 0041
Create Date: 2026-07-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "market_events",
        sa.Column("affected_games", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "market_events",
        sa.Column("impact_score", sa.Integer(), nullable=True),
    )
    op.add_column(
        "market_events",
        sa.Column("confidence_score", sa.Numeric(5, 2), nullable=True),
    )
    op.add_column(
        "daily_market_reports",
        sa.Column(
            "catalysts_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    op.execute(
        "UPDATE market_events "
        "SET affected_games = '[\"pokemon\"]'::jsonb "
        "WHERE affected_games IS NULL"
    )
    op.alter_column("market_events", "affected_games", nullable=False)
    op.create_check_constraint(
        "ck_market_events_affected_games_nonempty",
        "market_events",
        "jsonb_typeof(affected_games) = 'array' "
        "AND jsonb_array_length(affected_games) > 0",
    )
    op.create_check_constraint(
        "ck_market_events_impact_score_range",
        "market_events",
        "impact_score IS NULL OR impact_score BETWEEN 0 AND 100",
    )
    op.create_check_constraint(
        "ck_market_events_confidence_score_range",
        "market_events",
        "confidence_score IS NULL OR confidence_score BETWEEN 0 AND 100",
    )


def downgrade() -> None:
    op.drop_column("daily_market_reports", "catalysts_json")
    op.drop_constraint(
        "ck_market_events_confidence_score_range",
        "market_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_market_events_impact_score_range",
        "market_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_market_events_affected_games_nonempty",
        "market_events",
        type_="check",
    )
    op.drop_column("market_events", "confidence_score")
    op.drop_column("market_events", "impact_score")
    op.drop_column("market_events", "affected_games")
