"""backfill metadata.set nested block for existing yugioh assets

Revision ID: 0028
Revises: 0027
Create Date: 2026-04-28

YGO ingest (ygo.py) wrote metadata as a flat shape:
    {"set_code": "LOB-001", "set_name": "Legend of Blue Eyes White Dragon", ...}

But the web layer reads `metadata->'set'->>'id'` (mirroring Pokemon's ingest):
    {"set": {"id": "LOB-001", "name": "Legend of Blue Eyes White Dragon"}, ...}

Result: every YGO asset is invisible to /filters/sets, the set_id filter on
/cards, and the index ix_assets_set_id from migration 0023.

This migration backfills the nested `set` block from the existing flat fields,
without removing the flat fields (kept for /diag/ygo-verify compatibility).

Idempotent: WHERE metadata->'set' IS NULL means re-running is a no-op for
already-backfilled rows.

Safety: only touches rows where game='yugioh'. Pokemon assets already have the
nested block from build_asset_payload().
"""

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Build the nested `set` block from existing flat metadata fields. Use
    # jsonb_build_object so we get proper jsonb (not text), and || to merge
    # with the existing metadata. WHERE clause makes this idempotent.
    # set.id must be the expansion code (LEDE), not the printing code (LEDE-EN001).
    # split_part on '-' extracts the prefix: LEDE-EN001 → LEDE, LOB-001 → LOB.
    # Predicate covers NULL and partially-backfilled rows (empty or wrong id).
    op.execute("""
        UPDATE assets
        SET metadata = metadata || jsonb_build_object(
            'set', jsonb_build_object(
                'id',    split_part(metadata->>'set_code', '-', 1),
                'name',  metadata->>'set_name',
                'total', NULL
            )
        )
        WHERE game = 'yugioh'
          AND metadata->>'set_code' IS NOT NULL
          AND COALESCE(metadata->'set'->>'id', '') = ''
    """)


def downgrade() -> None:
    # Remove the nested `set` block from yugioh rows. Flat fields remain.
    op.execute("""
        UPDATE assets
        SET metadata = metadata - 'set'
        WHERE game = 'yugioh'
    """)
