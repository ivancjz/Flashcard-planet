"""Add ingestion staging, cache, and review tables.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-10 00:00:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "raw_listings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="ebay"),
        sa.Column("source_listing_id", sa.String(length=200), nullable=False),
        sa.Column("raw_title", sa.Text(), nullable=False),
        sa.Column("price_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("sold_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("currency_original", sa.String(length=8), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("mapped_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("match_method", sa.String(length=20), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_reason", sa.Text(), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'processed', 'failed', 'pending_ai')",
            name="ck_raw_listings_status",
        ),
        sa.ForeignKeyConstraint(["mapped_asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "source_listing_id", name="uq_raw_listings_source_source_listing_id"),
    )
    op.create_index(
        "idx_raw_listings_status_pending",
        "raw_listings",
        ["status"],
        unique=False,
        postgresql_where=sa.text("status = 'pending'"),
    )

    op.create_table(
        "asset_mapping_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("normalized_title", sa.String(length=500), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False),
        sa.Column("match_method", sa.String(length=20), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_hit_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_title"),
    )
    op.create_index("idx_mapping_cache_title", "asset_mapping_cache", ["normalized_title"])

    op.create_table(
        "human_review_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_title", sa.Text(), nullable=False),
        sa.Column("best_guess_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("best_guess_confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["best_guess_asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["raw_listing_id"], ["raw_listings.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("human_review_queue")
    op.drop_index("idx_mapping_cache_title", table_name="asset_mapping_cache")
    op.drop_table("asset_mapping_cache")
    op.drop_index("idx_raw_listings_status_pending", table_name="raw_listings")
    op.drop_table("raw_listings")
