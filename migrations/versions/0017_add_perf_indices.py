"""add composite index on price_history and game index on assets for web/cards query performance

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-24
"""
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_price_history_asset_source_captured",
        "price_history",
        ["asset_id", "source", "captured_at"],
    )
    op.create_index("ix_assets_game", "assets", ["game"])


def downgrade() -> None:
    op.drop_index("ix_assets_game", table_name="assets")
    op.drop_index("ix_price_history_asset_source_captured", table_name="price_history")
