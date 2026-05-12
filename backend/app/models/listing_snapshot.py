"""ListingSnapshot — stores from-price snapshots computed from eBay Browse API ask listings.

Ask prices MUST NOT enter price_history (per CLAUDE.md). This table is the
authoritative store for sealed product from-price observations.

Schema:
  asset_id     — FK to assets table (asset_class=SEALED)
  source       — always 'ebay_sealed_ask' for Browse API data
  captured_at  — UTC timestamp of the ingest run
  from_price   — median of ranks 2-6 by total landed price (item + shipping)
                 NULL when min_count_met=False
  listing_count — total listings returned by Browse API before filtering
  min_count_met — True when >=5 listings survived the outlier filter
  raw_snapshot  — JSONB: up to 10 listings [{item_id, title, price, shipping_cost, listing_url}]

Index: (asset_id, captured_at DESC) for 7-day trend queries.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.app.db.base import Base


class ListingSnapshot(Base):
    __tablename__ = "listing_snapshot"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="ebay_sealed_ask")
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    from_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    listing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    min_count_met: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    asset: Mapped["Asset"] = relationship(back_populates="listing_snapshots")  # type: ignore[name-defined]
