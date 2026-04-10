from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Iterable
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.app.ingestion.ebay.models import EbayListing
from backend.app.models.raw_listing import RawListing, RawListingStatus


def upsert_batch(db: Session, listings: Iterable[EbayListing]) -> int:
    values = [
        {
            "source": "ebay",
            "source_listing_id": listing.source_listing_id,
            "raw_title": listing.raw_title,
            "price_usd": listing.price_usd,
            "sold_at": listing.sold_at,
            "currency_original": listing.currency_original,
            "url": listing.url,
            "status": RawListingStatus.PENDING.value,
        }
        for listing in listings
    ]
    if not values:
        return 0

    stmt = insert(RawListing).values(values)
    stmt = stmt.on_conflict_do_nothing(index_elements=["source", "source_listing_id"])
    result = db.execute(stmt)
    db.commit()
    return int(result.rowcount or 0)


def load_pending(db: Session, limit: int) -> list[RawListing]:
    stmt = (
        select(RawListing)
        .where(RawListing.status == RawListingStatus.PENDING.value)
        .order_by(RawListing.ingested_at.asc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def mark_processed(
    db: Session,
    listing_id: UUID,
    asset_id: UUID,
    confidence: Decimal,
    method: str,
) -> None:
    is_failed = method == "noise_filtered"
    db.execute(
        update(RawListing)
        .where(RawListing.id == listing_id)
        .values(
            status=RawListingStatus.FAILED.value if is_failed else RawListingStatus.PROCESSED.value,
            mapped_asset_id=asset_id,
            confidence=confidence,
            match_method=method,
            processed_at=datetime.now(UTC),
            error_reason="noise_filtered" if is_failed else None,
        )
    )
