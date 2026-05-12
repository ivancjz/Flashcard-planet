"""GET /api/v1/sealed/products — from-price display for 20 curated sealed products.

No auth gate in Approach B.1. Free access to show Trung the product.
Add Pro gate after sealed pivot is validated (TASK-504 decision point).

7-day trend: compares latest snapshot vs closest snapshot to 7 days ago.
Shows NULL trend when no snapshot older than 1 day exists (< 7 days of data).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.models.asset import Asset
from backend.app.models.enums import AssetClass
from backend.app.models.listing_snapshot import ListingSnapshot

router = APIRouter(prefix="/api/v1/sealed", tags=["sealed"])


def _get_sealed_products(db: Session) -> list[dict[str, Any]]:
    """Fetch all SEALED assets with their latest snapshot and 7d-ago snapshot."""
    now = datetime.now(UTC)
    seven_days_ago = now - timedelta(days=7)
    one_day_ago = now - timedelta(days=1)

    # All SEALED assets
    assets = db.scalars(
        select(Asset)
        .where(Asset.asset_class == AssetClass.SEALED.value)
        .order_by(Asset.set_name, Asset.name)
    ).all()

    if not assets:
        return []

    asset_ids = [a.id for a in assets]
    asset_map = {a.id: a for a in assets}

    # Latest snapshot per asset (most recent captured_at)
    latest_subq = (
        select(
            ListingSnapshot.asset_id,
            func.max(ListingSnapshot.captured_at).label("max_captured_at"),
        )
        .where(ListingSnapshot.asset_id.in_(asset_ids))
        .group_by(ListingSnapshot.asset_id)
        .subquery()
    )
    latest_rows = db.execute(
        select(ListingSnapshot)
        .join(
            latest_subq,
            (ListingSnapshot.asset_id == latest_subq.c.asset_id) &
            (ListingSnapshot.captured_at == latest_subq.c.max_captured_at),
        )
    ).scalars().all()
    latest_map = {row.asset_id: row for row in latest_rows}

    # 7d-ago snapshot: find the closest snapshot to NOW()-7d within a ±12h window.
    # We fetch all candidates and find the closest in Python (avoids PG-specific epoch math).
    window_start = seven_days_ago - timedelta(hours=12)
    window_end = seven_days_ago + timedelta(hours=12)
    old_candidates = db.execute(
        select(ListingSnapshot)
        .where(
            ListingSnapshot.asset_id.in_(asset_ids),
            ListingSnapshot.captured_at >= window_start,
            ListingSnapshot.captured_at <= window_end,
        )
    ).scalars().all()
    # For each asset, keep the snapshot whose captured_at is closest to seven_days_ago
    old_map: dict[Any, ListingSnapshot] = {}
    for row in old_candidates:
        if row.asset_id not in old_map:
            old_map[row.asset_id] = row
        else:
            existing = old_map[row.asset_id]
            # Compare absolute distance to seven_days_ago
            existing_delta = abs((existing.captured_at.replace(tzinfo=UTC) - seven_days_ago).total_seconds())
            new_delta = abs((row.captured_at.replace(tzinfo=UTC) - seven_days_ago).total_seconds())
            if new_delta < existing_delta:
                old_map[row.asset_id] = row

    # Build response
    result = []
    for asset in assets:
        latest = latest_map.get(asset.id)
        old = old_map.get(asset.id)

        from_price = None
        trend_pct = None
        trend_label = None
        last_updated = None

        if latest and latest.min_count_met and latest.from_price is not None:
            from_price = float(latest.from_price)
            last_updated = latest.captured_at.isoformat() if latest.captured_at else None

            # Only show trend if we have a 7d-ago snapshot with valid price
            if old and old.min_count_met and old.from_price is not None and old.from_price > 0:
                delta = (latest.from_price - old.from_price) / old.from_price * 100
                trend_pct = round(float(delta), 1)
            elif latest.captured_at and latest.captured_at.replace(tzinfo=UTC) < one_day_ago:
                # We have data but no 7d-ago snapshot yet
                trend_label = "< 7 days data"

        result.append({
            "asset_id": str(asset.id),
            "name": asset.name,
            "set_name": asset.set_name,
            "product_type": asset.product_type,
            "game": asset.game,
            "from_price": from_price,
            "trend_pct": trend_pct,
            "trend_label": trend_label,
            "last_updated": last_updated,
            "listing_count": latest.listing_count if latest else 0,
            "min_count_met": latest.min_count_met if latest else False,
        })

    return result


@router.get("/products")
def get_sealed_products(db: Session = Depends(get_database)) -> dict[str, Any]:
    """Return from-price and 7-day trend for all curated sealed products.

    No auth gate — free tier access for Approach B.1 (Trung demo).
    """
    products = _get_sealed_products(db)
    return {
        "products": products,
        "count": len(products),
    }
