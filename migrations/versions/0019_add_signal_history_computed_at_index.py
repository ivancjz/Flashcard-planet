"""add index on asset_signal_history.computed_at for alerts query

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-24

The /api/v1/web/alerts endpoint rewrote LAG-over-full-table to a LATERAL
lookup. The existing (asset_id, computed_at) index serves the LATERAL.
This index on bare computed_at DESC lets the outer ORDER BY / early-stop
scan from newest to oldest without processing all rows.
"""
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_asset_signal_history_computed_at"
        " ON asset_signal_history (computed_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_asset_signal_history_computed_at")
