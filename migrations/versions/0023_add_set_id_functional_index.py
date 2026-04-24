"""add functional index on assets metadata->set->id for set filter

Revision ID: 0023
Revises: 0022
Create Date: 2026-04-24

Speeds up ILIKE and equality queries on a.metadata->'set'->>'id'
used by the /filters/sets endpoint and the set_id filter on /cards.
"""
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_assets_set_id"
        " ON assets ((metadata->'set'->>'id'))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_assets_set_id")
