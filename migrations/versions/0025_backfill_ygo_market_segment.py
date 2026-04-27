"""backfill market_segment='raw' for ygoprodeck_api rows

Revision ID: 0025
Revises: 0024
Create Date: 2026-04-27

YGO ingestion (ygo.py) did not set market_segment on PriceHistory inserts.
PR B's signal engine filter (market_segment = 'raw') therefore excluded all
134 existing ygoprodeck_api rows, leaving all 67 YGO assets in INSUFFICIENT_DATA.

This migration backfills existing rows.  The ingest fix (adding market_segment='raw'
to pg_insert in ygo.py) ensures future writes are correct.

Idempotent: WHERE market_segment IS NULL means re-running is a no-op.
"""

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE price_history
        SET market_segment = 'raw'
        WHERE source = 'ygoprodeck_api'
          AND market_segment IS NULL
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE price_history
        SET market_segment = NULL
        WHERE source = 'ygoprodeck_api'
    """)
