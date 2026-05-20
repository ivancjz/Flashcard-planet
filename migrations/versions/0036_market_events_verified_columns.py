"""add verified_at and verified_by to market_events

Revision ID: 0036
Revises: 0035
Create Date: 2026-05-20

Adds audit columns to market_events to distinguish machine-verified events
(source URL audited by AI) from events that merely have a URL present.
Service layer should set both columns on any new insert that passes audit.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.add_column(
        "market_events",
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "market_events",
        sa.Column("verified_by", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("market_events", "verified_by")
    op.drop_column("market_events", "verified_at")
