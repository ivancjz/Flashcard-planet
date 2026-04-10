from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from backend.app.db.base import Base


class RawListingStatus(str, Enum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"
    PENDING_AI = "pending_ai"


class RawListing(Base):
    __tablename__ = "raw_listings"
    __table_args__ = (
        UniqueConstraint("source", "source_listing_id", name="uq_raw_listings_source_source_listing_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="ebay")
    source_listing_id: Mapped[str] = mapped_column(String(200), nullable=False)
    raw_title: Mapped[str] = mapped_column(Text, nullable=False)
    price_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    sold_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    currency_original: Mapped[str | None] = mapped_column(String(8))
    url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=RawListingStatus.PENDING.value)
    mapped_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id"))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    match_method: Mapped[str | None] = mapped_column(String(20))
    failure_count: Mapped[int] = mapped_column(default=0, nullable=False)
    error_reason: Mapped[str | None] = mapped_column(Text)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


Index(
    "idx_raw_listings_status_pending",
    RawListing.status,
    postgresql_where=(RawListing.status == RawListingStatus.PENDING.value),
)
