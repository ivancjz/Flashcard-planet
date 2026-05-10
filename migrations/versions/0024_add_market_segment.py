"""add market_segment, grade_company, grade_score to price_history and observation_match_logs

Revision ID: 0024
Revises: 0023
Create Date: 2026-04-27

Adds per-row market segment classification columns.  All existing
pokemon_tcg_api rows are immediately backfilled to 'raw' (they always
represent raw card prices).  eBay rows stay NULL until the separate
backfill script (scripts/backfill_market_segment.py) is run.
"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # price_history
    op.add_column('price_history', sa.Column('market_segment', sa.Text(), nullable=True))
    op.add_column('price_history', sa.Column('grade_company', sa.Text(), nullable=True))
    op.add_column('price_history', sa.Column('grade_score', sa.Text(), nullable=True))

    # observation_match_logs
    op.add_column('observation_match_logs', sa.Column('market_segment', sa.Text(), nullable=True))
    op.add_column('observation_match_logs', sa.Column('grade_company', sa.Text(), nullable=True))
    op.add_column('observation_match_logs', sa.Column('grade_score', sa.Text(), nullable=True))

    # Index for signal engine's primary query pattern (asset_id + source + segment + recency)
    op.execute(
        "CREATE INDEX ix_price_history_segment_lookup"
        " ON price_history (asset_id, source, market_segment, captured_at DESC)"
    )

    # Backfill TCG API rows immediately — they are always raw
    op.execute("""
        UPDATE price_history
        SET market_segment = 'raw'
        WHERE source = 'pokemon_tcg_api'
          AND market_segment IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_price_history_segment_lookup")
    op.drop_column('price_history', 'grade_score')
    op.drop_column('price_history', 'grade_company')
    op.drop_column('price_history', 'market_segment')
    op.drop_column('observation_match_logs', 'grade_score')
    op.drop_column('observation_match_logs', 'grade_company')
    op.drop_column('observation_match_logs', 'market_segment')
