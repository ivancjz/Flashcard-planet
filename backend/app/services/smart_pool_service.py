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
                name=row.name,
                set_name=row.set_name,
                price_change_count_7d=int(row.change_count),
                latest_price=latest,
                earliest_price_7d=min_price,
                price_range_pct=price_range_pct,
            )
        )

    candidates.sort(key=lambda item: item.price_change_count_7d, reverse=True)
    logger.info(
        "smart_pool_candidates_loaded",
        extra={
            "candidate_count": len(candidates),
            "top_n": top_n,
            "min_change_count": min_change_count,
        },
    )
    return candidates
