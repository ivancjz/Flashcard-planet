"""add pg_trgm extension and trigram index on assets.name for search

Revision ID: 0022
Revises: 0021
Create Date: 2026-04-24

Enables ILIKE '%foo%' queries on assets.name to use a GIN trigram index
instead of a full sequential scan. Assets table is ~5k rows so this is
a safety measure for future growth rather than an immediate requirement.
"""
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_assets_name_trgm"
        " ON assets USING gin (name gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_assets_name_trgm")
