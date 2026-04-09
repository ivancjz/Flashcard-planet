from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.price_sources import get_active_price_source_filter
from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory
from backend.app.services.liquidity_service import get_liquidity_snapshots

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SmartPoolCandidate:
    asset_id: Any
    name: str
    set_name: str | None
    price_change_count_7d: int
    latest_price: Decimal | None
    earliest_price_7d: Decimal | None
    price_range_pct: Decimal | None
    external_id: str | None = None
    liquidity_score: float = 0.0
    composite_score: float = 0.0


def get_smart_pool_candidates(
    db: Session,
    *,
    top_n: int = 10,
    min_change_count: int = 2,
) -> list[SmartPoolCandidate]:
    cutoff = datetime.now(UTC) - timedelta(days=7)
    source_filter = get_active_price_source_filter(db)
    activity = (
        select(
            PriceHistory.asset_id.label("asset_id"),
            func.count().label("change_count"),
            func.min(PriceHistory.price).label("min_price"),
            func.max(PriceHistory.price).label("max_price"),
            func.max(PriceHistory.captured_at).label("latest_at"),
        )
        .where(
            source_filter,
            PriceHistory.captured_at >= cutoff,
        )
        .group_by(PriceHistory.asset_id)
        .having(func.count() >= min_change_count)
        .order_by(func.count().desc())
        .limit(top_n)
        .subquery()
    )
    latest_price = (
        select(
            PriceHistory.asset_id.label("asset_id"),
            PriceHistory.price.label("latest_price"),
            func.row_number()
            .over(
                partition_by=PriceHistory.asset_id,
                order_by=PriceHistory.captured_at.desc(),
            )
            .label("price_rank"),
        )
        .where(
            source_filter,
            PriceHistory.captured_at >= cutoff,
        )
        .subquery()
    )
    rows = db.execute(
        select(
            Asset.id,
            Asset.external_id,
            Asset.name,
            Asset.set_name,
            activity.c.change_count,
            activity.c.min_price,
            activity.c.max_price,
            latest_price.c.latest_price,
        )
        .join(activity, activity.c.asset_id == Asset.id)
        .join(
            latest_price,
            latest_price.c.asset_id == Asset.id,
        )
        .where(latest_price.c.price_rank == 1)
        .order_by(activity.c.change_count.desc(), Asset.name.asc())
    ).all()

    candidates: list[SmartPoolCandidate] = []
    for row in rows:
        min_price = Decimal(row.min_price) if row.min_price is not None else None
        max_price = Decimal(row.max_price) if row.max_price is not None else None
        latest = Decimal(row.latest_price) if row.latest_price is not None else None
        price_range_pct = None
        if min_price is not None and max_price is not None and min_price > 0:
            price_range_pct = (
                ((max_price - min_price) / min_price) * Decimal("100")
            ).quantize(Decimal("0.01"))
        candidates.append(
            SmartPoolCandidate(
                asset_id=row.id,
                external_id=getattr(row, "external_id", None),
                name=row.name,
                set_name=row.set_name,
                price_change_count_7d=int(row.change_count),
                latest_price=latest,
                earliest_price_7d=min_price,
                price_range_pct=price_range_pct,
            )
        )

    try:
        liquidity_snapshots = get_liquidity_snapshots(db, asset_ids=[candidate.asset_id for candidate in candidates])
    except Exception:
        liquidity_snapshots = {}
    enriched_candidates: list[SmartPoolCandidate] = []
    for candidate in candidates:
        liquidity_snapshot = liquidity_snapshots.get(candidate.asset_id)
        liquidity_score = float(liquidity_snapshot.liquidity_score) if liquidity_snapshot is not None else 0.0
        composite_score = (candidate.price_change_count_7d * 0.6) + (liquidity_score * 0.4)
        enriched_candidates.append(
            SmartPoolCandidate(
                asset_id=candidate.asset_id,
                external_id=candidate.external_id,
                name=candidate.name,
                set_name=candidate.set_name,
                price_change_count_7d=candidate.price_change_count_7d,
                latest_price=candidate.latest_price,
                earliest_price_7d=candidate.earliest_price_7d,
                price_range_pct=candidate.price_range_pct,
                liquidity_score=liquidity_score,
                composite_score=composite_score,
            )
        )

    enriched_candidates.sort(key=lambda item: item.composite_score, reverse=True)
    logger.info(
        "smart_pool_candidates_loaded",
        extra={
            "candidate_count": len(enriched_candidates),
            "top_n": top_n,
            "min_change_count": min_change_count,
        },
    )
    return enriched_candidates
