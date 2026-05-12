"""add sealed product tables (listing_snapshot + product_type on assets)

Revision ID: 0034
Revises: 0033
Create Date: 2026-05-12

Adds:
- listing_snapshot table for eBay Browse API ask-price snapshots
  (sealed products only; ask prices MUST NOT enter price_history)
- product_type nullable column on assets (booster_box, etb, case, blister, other)

All changes are additive and fully backward-compatible with existing rows.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # product_type: nullable, NOT in UniqueConstraint
    op.add_column("assets", sa.Column(
        "product_type", sa.String(32), nullable=True
    ))

    # listing_snapshot table — ask-price snapshots for sealed products
    op.create_table(
        "listing_snapshot",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_id", UUID(as_uuid=True),
                  sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(64), nullable=False, server_default="ebay_sealed_ask"),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("from_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("listing_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("min_count_met", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("raw_snapshot", JSONB, nullable=True),
    )
    op.create_index(
        "ix_listing_snapshot_asset_time",
        "listing_snapshot",
        ["asset_id", sa.text("captured_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_listing_snapshot_asset_time", table_name="listing_snapshot")
    op.drop_table("listing_snapshot")
    op.drop_column("assets", "product_type")
