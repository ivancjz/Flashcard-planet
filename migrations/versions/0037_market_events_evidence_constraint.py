"""Require source_url + verified_at on all market_events rows (evidence discipline).

All 13 existing rows already have both fields populated (verified 2026-05-23).
"""

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    # Idempotent — constraint may already exist if applied directly against prod.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'market_events_evidence_required'
            ) THEN
                ALTER TABLE market_events
                ADD CONSTRAINT market_events_evidence_required
                CHECK (source_url IS NOT NULL AND verified_at IS NOT NULL);
            END IF;
        END $$
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE market_events
        DROP CONSTRAINT IF EXISTS market_events_evidence_required
    """)
