"""ensure composite index on price_history and game index on assets

Revision ID: 0018
Revises: 0017
Create Date: 2026-04-24

0017 may have failed silently on some deploys. This migration uses
IF NOT EXISTS so it is safe to run whether or not 0017 applied.
"""
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_price_history_asset_source_captured"
        " ON price_history (asset_id, source, captured_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_assets_game ON assets (game)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_assets_game")
    op.execute("DROP INDEX IF EXISTS ix_price_history_asset_source_captured")
