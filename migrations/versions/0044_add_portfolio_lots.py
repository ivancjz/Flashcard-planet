"""add portfolio lots

Revision ID: 0044
Revises: 0043
Create Date: 2026-07-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_lots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "asset_id",
            UUID(as_uuid=True),
            sa.ForeignKey("assets.id"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_cost_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("purchased_on", sa.Date(), nullable=False),
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
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_portfolio_lots_quantity_positive",
        ),
        sa.CheckConstraint(
            "unit_cost_usd >= 0",
            name="ck_portfolio_lots_unit_cost_non_negative",
        ),
    )
    op.create_index(
        "ix_portfolio_lots_user_asset",
        "portfolio_lots",
        ["user_id", "asset_id"],
    )
    op.create_index(
        "ix_portfolio_lots_user_purchased_on",
        "portfolio_lots",
        ["user_id", sa.text("purchased_on DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_portfolio_lots_user_purchased_on",
        table_name="portfolio_lots",
    )
    op.drop_index(
        "ix_portfolio_lots_user_asset",
        table_name="portfolio_lots",
    )
    op.drop_table("portfolio_lots")
