"""Flashcard Planet monitors not only price changes, but the credibility of those changes under real market activity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from backend.app.core.price_sources import EBAY_SOLD_PRICE_SOURCE, SAMPLE_PRICE_SOURCE
from backend.app.models.price_history import PriceHistory

HIGH_LIQUIDITY_LABEL = "High Liquidity"
MEDIUM_LIQUIDITY_LABEL = "Medium Liquidity"
LOW_LIQUIDITY_LABEL = "Low Liquidity"

HIGH_CONFIDENCE_LABEL = "High Confidence"
MEDIUM_CONFIDENCE_LABEL = "Medium Confidence"
LOW_CONFIDENCE_LABEL = "Low Confidence"


@dataclass(frozen=True)
class LiquiditySnapshot:
    asset_id: Any
    sales_count_7d: int
    sales_count_30d: int
    days_since_last_sale: int | None
    last_real_sale_at: datetime | None
    history_depth: int
    source_count: int
    liquidity_score: int
    liquidity_label: str


@dataclass(frozen=True)
class AssetSignalSnapshot:
    asset_id: Any
    sales_count_7d: int
    sales_count_30d: int
    days_since_last_sale: int | None
    last_real_sale_at: datetime | None
    history_depth: int
    source_count: int
    liquidity_score: int
    liquidity_label: str
    price_move_magnitude: Decimal | None
    alert_confidence: int | None
    alert_confidence_label: str | None


def _coerce_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _coerce_now(now: datetime | None = None) -> datetime:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        return current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


def _normalize_asset_ids(asset_ids: Iterable[Any]) -> list[Any]:
    unique_ids: list[Any] = []
    seen: set[Any] = set()
    for asset_id in asset_ids:
        if asset_id in seen:
            continue
        seen.add(asset_id)
        unique_ids.append(asset_id)
    return unique_ids


def score_sales_count_7d(value: int) -> int:
    if value <= 0:
        return 0
    if value == 1:
        return 25
    if value <= 3:
        return 50
    if value <= 6:
        return 75
    return 100


def score_sales_count_30d(value: int) -> int:
    if value <= 0:
        return 0
    if value <= 2:
        return 25
    if value <= 5:
        return 50
    if value <= 10:
        return 75
    return 100


def score_days_since_last_sale(value: int | None) -> int:
    if value is None:
        return 0
    if value <= 2:
        return 100
    if value <= 7:
        return 75
    if value <= 14:
        return 50
    if value <= 30:
        return 25
    return 0


def score_history_depth(value: int) -> int:
    if value <= 0:
        return 0
    if value <= 2:
        return 20
    if value <= 5:
        return 40
    if value <= 10:
        return 70
    return 100


def score_source_count(value: int) -> int:
    if value <= 0:
        return 0
    if value == 1:
        return 50
    if value == 2:
        return 80
    return 100


def compute_liquidity_score(
    *,
    sales_count_7d: int,
    sales_count_30d: int,
    days_since_last_sale: int | None,
    history_depth: int,
    source_count: int,
) -> int:
    weighted_score = (
        (score_sales_count_7d(sales_count_7d) * 0.30)
        + (score_sales_count_30d(sales_count_30d) * 0.25)
        + (score_days_since_last_sale(days_since_last_sale) * 0.20)
        + (score_history_depth(history_depth) * 0.15)
        + (score_source_count(source_count) * 0.10)
    )
    return int(round(weighted_score))


def classify_liquidity_label(score: int) -> str:
    if score >= 80:
        return HIGH_LIQUIDITY_LABEL
    if score >= 50:
        return MEDIUM_LIQUIDITY_LABEL
    return LOW_LIQUIDITY_LABEL


def score_price_move_magnitude(percent_change: Decimal | float | int) -> int:
    magnitude = abs(Decimal(str(percent_change)))
    if magnitude < Decimal("3"):
        return 10
    if magnitude <= Decimal("5"):
        return 30
    if magnitude <= Decimal("10"):
        return 60
    if magnitude <= Decimal("20"):
        return 85
    return 100


def _price_direction(current_price: Decimal, previous_price: Decimal) -> int:
    if current_price > previous_price:
        return 1
    if current_price < previous_price:
        return -1
    return 0


def score_source_agreement(source_count: int, source_directions: list[int]) -> int:
    if source_count <= 0:
        return 0
    if source_count == 1:
        return 50

    non_flat_directions = [direction for direction in source_directions if direction != 0]
    if len(non_flat_directions) >= 2 and len(non_flat_directions) == source_count:
        if len(set(non_flat_directions)) == 1:
            return 85
        return 30

    # Multiple sources exist, but the latest directional evidence is incomplete or mixed.
    return 30


def score_outlier_handling(snapshot: LiquiditySnapshot) -> int:
    # Low-volume moves can be misleading, so shallow or stale histories are suppressed on purpose.
    if snapshot.history_depth <= 0 or snapshot.sales_count_30d <= 0 or snapshot.days_since_last_sale is None:
        return 20
    if snapshot.history_depth < 3 or snapshot.sales_count_7d <= 1 or snapshot.sales_count_30d < 2:
        return 30
    if snapshot.history_depth < 5 or snapshot.sales_count_30d < 3 or snapshot.days_since_last_sale > 14:
        return 60
    return 90


def compute_alert_confidence(
    *,
    price_move_magnitude: Decimal | float | int,
    liquidity_score: int,
    source_agreement: int,
    outlier_handling: int,
) -> int:
    weighted_score = (
        (score_price_move_magnitude(price_move_magnitude) * 0.25)
        + (liquidity_score * 0.35)
        + (source_agreement * 0.20)
        + (outlier_handling * 0.20)
    )
    return int(round(weighted_score))


def classify_alert_confidence_label(score: int) -> str:
    if score >= 75:
        return HIGH_CONFIDENCE_LABEL
    if score >= 45:
        return MEDIUM_CONFIDENCE_LABEL
    return LOW_CONFIDENCE_LABEL


def _days_since(reference_now: datetime, latest_timestamp: datetime | None) -> int | None:
    latest = _coerce_utc(latest_timestamp)
    if latest is None:
        return None
    delta = reference_now - latest
    if delta.total_seconds() < 0:
        return 0
    return int(delta.total_seconds() // 86400)


def get_liquidity_snapshots(
    db: Session,
    asset_ids: Iterable[Any],
    *,
    now: datetime | None = None,
) -> dict[Any, LiquiditySnapshot]:
    normalized_asset_ids = _normalize_asset_ids(asset_ids)
    if not normalized_asset_ids:
        return {}

    reference_now = _coerce_now(now)
    cutoff_7d = reference_now - timedelta(days=7)
    cutoff_30d = reference_now - timedelta(days=30)

    # The current schema stores point-in-time provider observations, not explicit sale events.
    # For this MVP, "sales" is the closest grounded proxy: count real non-sample observations.
    rows = db.execute(
        select(
            PriceHistory.asset_id,
            func.sum(case(
                (and_(PriceHistory.source == EBAY_SOLD_PRICE_SOURCE,
                      PriceHistory.captured_at >= cutoff_7d), 1),
                else_=0,
            )).label("sales_count_7d"),
            func.sum(case(
                (and_(PriceHistory.source == EBAY_SOLD_PRICE_SOURCE,
                      PriceHistory.captured_at >= cutoff_30d), 1),
                else_=0,
            )).label("sales_count_30d"),
            func.count(PriceHistory.id).label("history_depth"),
            func.max(case(
                (PriceHistory.source == EBAY_SOLD_PRICE_SOURCE, PriceHistory.captured_at),
                else_=None,
            )).label("last_real_sale_at"),
            func.count(func.distinct(PriceHistory.source)).label("source_count"),
        )
        .where(
            PriceHistory.asset_id.in_(normalized_asset_ids),
            PriceHistory.source != SAMPLE_PRICE_SOURCE,
        )
        .group_by(PriceHistory.asset_id)
    ).all()

    raw_stats_by_asset = {
        row.asset_id: row
        for row in rows
    }
    snapshots: dict[Any, LiquiditySnapshot] = {}
    for asset_id in normalized_asset_ids:
        row = raw_stats_by_asset.get(asset_id)
        sales_count_7d = int(row.sales_count_7d or 0) if row is not None else 0
        sales_count_30d = int(row.sales_count_30d or 0) if row is not None else 0
        history_depth = int(row.history_depth or 0) if row is not None else 0
        source_count = int(row.source_count or 0) if row is not None else 0
        last_real_sale_at = _coerce_utc(row.last_real_sale_at if row is not None else None)
        days_since_last_sale = _days_since(reference_now, last_real_sale_at)
        liquidity_score = compute_liquidity_score(
            sales_count_7d=sales_count_7d,
            sales_count_30d=sales_count_30d,
            days_since_last_sale=days_since_last_sale,
            history_depth=history_depth,
            source_count=source_count,
        )
        snapshots[asset_id] = LiquiditySnapshot(
            asset_id=asset_id,
            sales_count_7d=sales_count_7d,
            sales_count_30d=sales_count_30d,
            days_since_last_sale=days_since_last_sale,
            last_real_sale_at=last_real_sale_at,
            history_depth=history_depth,
            source_count=source_count,
            liquidity_score=liquidity_score,
            liquidity_label=classify_liquidity_label(liquidity_score),
        )
    return snapshots


def get_latest_source_directions(
    db: Session,
    asset_ids: Iterable[Any],
) -> dict[Any, list[int]]:
    normalized_asset_ids = _normalize_asset_ids(asset_ids)
    if not normalized_asset_ids:
        return {}

    ranked = (
        select(
            PriceHistory.asset_id,
            PriceHistory.source,
            PriceHistory.price,
            func.row_number()
            .over(
                partition_by=(PriceHistory.asset_id, PriceHistory.source),
                order_by=PriceHistory.captured_at.desc(),
            )
            .label("source_rank"),
        )
        .where(
            PriceHistory.asset_id.in_(normalized_asset_ids),
            PriceHistory.source != SAMPLE_PRICE_SOURCE,
        )
        .subquery()
    )

    rows = db.execute(
        select(
            ranked.c.asset_id,
            ranked.c.source,
            ranked.c.price,
            ranked.c.source_rank,
        )
        .where(ranked.c.source_rank <= 2)
        .order_by(ranked.c.asset_id.asc(), ranked.c.source.asc(), ranked.c.source_rank.asc())
    ).all()

    grouped: dict[Any, dict[str, list[Decimal]]] = {}
    for row in rows:
        grouped.setdefault(row.asset_id, {}).setdefault(row.source, []).append(Decimal(row.price))

    directions_by_asset: dict[Any, list[int]] = {}
    for asset_id, sources in grouped.items():
        directions_by_asset[asset_id] = [
            _price_direction(prices[0], prices[1])
            for prices in sources.values()
            if len(prices) >= 2
        ]
    return directions_by_asset


def get_asset_signal_snapshots(
    db: Session,
    asset_ids: Iterable[Any],
    *,
    percent_changes_by_asset: dict[Any, Decimal] | None = None,
    now: datetime | None = None,
) -> dict[Any, AssetSignalSnapshot]:
    liquidity_snapshots = get_liquidity_snapshots(db, asset_ids, now=now)
    source_directions = get_latest_source_directions(db, asset_ids)
    signal_snapshots: dict[Any, AssetSignalSnapshot] = {}

    for asset_id, liquidity_snapshot in liquidity_snapshots.items():
        percent_change = None
        alert_confidence = None
        alert_confidence_label = None
        if percent_changes_by_asset is not None and asset_id in percent_changes_by_asset:
            percent_change = abs(Decimal(str(percent_changes_by_asset[asset_id]))).quantize(Decimal("0.01"))
            source_agreement = score_source_agreement(
                liquidity_snapshot.source_count,
                source_directions.get(asset_id, []),
            )
            outlier_handling = score_outlier_handling(liquidity_snapshot)
            alert_confidence = compute_alert_confidence(
                price_move_magnitude=percent_change,
                liquidity_score=liquidity_snapshot.liquidity_score,
                source_agreement=source_agreement,
                outlier_handling=outlier_handling,
            )
            alert_confidence_label = classify_alert_confidence_label(alert_confidence)

        signal_snapshots[asset_id] = AssetSignalSnapshot(
            asset_id=asset_id,
            sales_count_7d=liquidity_snapshot.sales_count_7d,
            sales_count_30d=liquidity_snapshot.sales_count_30d,
            days_since_last_sale=liquidity_snapshot.days_since_last_sale,
            last_real_sale_at=liquidity_snapshot.last_real_sale_at,
            history_depth=liquidity_snapshot.history_depth,
            source_count=liquidity_snapshot.source_count,
            liquidity_score=liquidity_snapshot.liquidity_score,
            liquidity_label=liquidity_snapshot.liquidity_label,
            price_move_magnitude=percent_change,
            alert_confidence=alert_confidence,
            alert_confidence_label=alert_confidence_label,
        )
    return signal_snapshots


def is_top_mover_eligible(snapshot: AssetSignalSnapshot) -> bool:
    # Main mover lists should highlight credible moves, not thin one-off prints.
    return (
        snapshot.sales_count_30d >= 3
        and snapshot.history_depth >= 5
        and snapshot.days_since_last_sale is not None
        and snapshot.days_since_last_sale <= 14
    )
