"""add partial index on asset_signal_history for transition rows only

Revision ID: 0021
Revises: 0020
Create Date: 2026-04-24

Partial index on (computed_at DESC) WHERE previous_label IS NOT NULL.
Covers only the rows that the /alerts query reads — transition rows.
Pre-migration rows (previous_label=NULL) are excluded from the index
and are also excluded from query results, so zero scan wasted on old rows.
"""
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_asset_signal_history_transitions"
        " ON asset_signal_history (computed_at DESC)"
        " WHERE previous_label IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_asset_signal_history_transitions")
