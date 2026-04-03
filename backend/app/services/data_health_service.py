from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from backend.app.core.price_sources import get_active_price_source_filter, get_configured_price_providers
from backend.app.core.tracked_pools import get_tracked_pokemon_pools
from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory
from backend.app.services.asset_tagging import (
    TAG_DIMENSION_LABELS,
    TAG_DIMENSION_ORDER,
    get_asset_tag_values,
    get_tag_value_sort_key,
)

PROVIDER_EXTERNAL_ID_PREFIX = "pokemontcg:%"


def _coerce_datetime_to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@dataclass
class AssetCoverageSnapshot:
    name: str
    external_id: str | None
    real_history_points: int
    latest_captured_at: datetime | None


@dataclass
class AssetMovementSnapshot:
    name: str
    external_id: str | None
    changed_rows_last_24h: int
    changed_rows_last_7d: int
    rows_last_7d: int
    distinct_real_prices: int
    latest_captured_at: datetime | None


@dataclass
class PoolHealthSnapshot:
    key: str
    label: str
    asset_prefix_like: str
    total_assets: int
    assets_with_real_history: int
    assets_without_real_history: int
    average_real_history_points_per_asset: Decimal
    assets_with_fewer_than_3_real_points: int
    assets_with_fewer_than_5_real_points: int
    assets_with_fewer_than_8_real_points: int
    recent_real_price_rows_last_24h: int
    recent_real_price_rows_last_7d: int
    recent_comparable_rows_last_24h: int
    recent_rows_with_price_change_last_24h: int
    percent_recent_rows_changed_last_24h: Decimal
    recent_comparable_rows_last_7d: int
    recent_rows_with_price_change_last_7d: int
    percent_recent_rows_changed_last_7d: Decimal
    assets_with_price_change_last_24h: int
    assets_with_price_change_last_7d: int
    assets_with_no_price_movement_full_history: int
    assets_with_unchanged_latest_price: int
    average_recent_rows_per_asset_last_24h: Decimal
    average_recent_rows_per_asset_last_7d: Decimal
    average_changed_rows_per_asset_last_24h: Decimal
    average_changed_rows_per_asset_last_7d: Decimal
    rows_per_recent_price_change_last_24h: Decimal | None
    rows_per_recent_price_change_last_7d: Decimal | None
    low_coverage_assets: list[AssetCoverageSnapshot] = field(default_factory=list)
    unchanged_latest_assets: list[str] = field(default_factory=list)
    high_activity_assets: list[AssetMovementSnapshot] = field(default_factory=list)
    low_activity_assets: list[AssetMovementSnapshot] = field(default_factory=list)


@dataclass
class TagHealthSnapshot:
    dimension: str
    dimension_label: str
    tag_value: str
    total_assets: int
    assets_with_real_history: int
    average_real_history_points_per_asset: Decimal
    assets_with_price_change_last_24h: int
    assets_with_price_change_last_7d: int
    recent_comparable_rows_last_24h: int
    recent_rows_with_price_change_last_24h: int
    percent_recent_rows_changed_last_24h: Decimal
    recent_comparable_rows_last_7d: int
    recent_rows_with_price_change_last_7d: int
    percent_recent_rows_changed_last_7d: Decimal
    assets_with_no_price_movement_full_history: int
    assets_with_unchanged_latest_price: int


@dataclass
class ProviderHealthSnapshot:
    slot: str
    source: str
    label: str
    is_primary: bool
    total_assets: int
    assets_with_real_history: int
    assets_without_real_history: int
    average_real_history_points_per_asset: Decimal
    assets_with_fewer_than_3_real_points: int
    assets_with_fewer_than_5_real_points: int
    assets_with_fewer_than_8_real_points: int
    recent_real_price_rows_last_24h: int
    recent_real_price_rows_last_7d: int
    recent_comparable_rows_last_24h: int
    recent_rows_with_price_change_last_24h: int
    percent_recent_rows_changed_last_24h: Decimal
    recent_comparable_rows_last_7d: int
    recent_rows_with_price_change_last_7d: int
    percent_recent_rows_changed_last_7d: Decimal
    assets_with_price_change_last_24h: int
    assets_with_price_change_last_7d: int
    assets_with_no_price_movement_full_history: int
    assets_with_unchanged_latest_price: int
    average_recent_rows_per_asset_last_24h: Decimal
    average_recent_rows_per_asset_last_7d: Decimal
    average_changed_rows_per_asset_last_24h: Decimal
    average_changed_rows_per_asset_last_7d: Decimal
    rows_per_recent_price_change_last_24h: Decimal | None
    rows_per_recent_price_change_last_7d: Decimal | None
    low_coverage_assets: list[AssetCoverageSnapshot] = field(default_factory=list)
    unchanged_latest_assets: list[str] = field(default_factory=list)
    high_activity_assets: list[AssetMovementSnapshot] = field(default_factory=list)
    low_activity_assets: list[AssetMovementSnapshot] = field(default_factory=list)
    pool_reports: list[PoolHealthSnapshot] = field(default_factory=list)
    tag_reports: list[TagHealthSnapshot] = field(default_factory=list)


@dataclass
class _AssetTagMetricRecord:
    asset: Asset
    history_points: int
    latest_captured_at: datetime | None
    recent_real_rows_last_24h: int
    recent_real_rows_last_7d: int
    recent_comparable_rows_last_24h: int
    recent_rows_with_price_change_last_24h: int
    recent_comparable_rows_last_7d: int
    recent_rows_with_price_change_last_7d: int
    distinct_real_prices: int
    latest_two_prices_unchanged: bool


@dataclass
class DataHealthReport:
    total_assets: int
    assets_with_real_history: int
    assets_without_real_history: int
    average_real_history_points_per_asset: Decimal
    assets_with_fewer_than_3_real_points: int
    assets_with_fewer_than_5_real_points: int
    assets_with_fewer_than_8_real_points: int
    recent_real_price_rows_last_24h: int
    recent_real_price_rows_last_7d: int
    recent_comparable_rows_last_24h: int
    recent_rows_with_price_change_last_24h: int
    percent_recent_rows_changed_last_24h: Decimal
    recent_comparable_rows_last_7d: int
    recent_rows_with_price_change_last_7d: int
    percent_recent_rows_changed_last_7d: Decimal
    assets_with_price_change_last_24h: int
    assets_with_price_change_last_7d: int
    assets_with_no_price_movement_full_history: int
    assets_with_unchanged_latest_price: int
    average_recent_rows_per_asset_last_24h: Decimal
    average_recent_rows_per_asset_last_7d: Decimal
    average_changed_rows_per_asset_last_24h: Decimal
    average_changed_rows_per_asset_last_7d: Decimal
    rows_per_recent_price_change_last_24h: Decimal | None
    rows_per_recent_price_change_last_7d: Decimal | None
    low_coverage_assets: list[AssetCoverageSnapshot] = field(default_factory=list)
    unchanged_latest_assets: list[str] = field(default_factory=list)
    high_activity_assets: list[AssetMovementSnapshot] = field(default_factory=list)
    low_activity_assets: list[AssetMovementSnapshot] = field(default_factory=list)
    pool_reports: list[PoolHealthSnapshot] = field(default_factory=list)
    tag_reports: list[TagHealthSnapshot] = field(default_factory=list)
    provider_reports: list[ProviderHealthSnapshot] = field(default_factory=list)


def _real_history_counts_subquery(source_filter, asset_like_prefix: str = PROVIDER_EXTERNAL_ID_PREFIX):
    return (
        select(
            PriceHistory.asset_id.label("asset_id"),
            func.count(PriceHistory.id).label("real_history_points"),
            func.max(PriceHistory.captured_at).label("latest_captured_at"),
        )
        .join(Asset, Asset.id == PriceHistory.asset_id)
        .where(source_filter)
        .where(Asset.external_id.like(asset_like_prefix))
        .group_by(PriceHistory.asset_id)
        .subquery()
    )


def _latest_two_ranked_subquery(source_filter, asset_like_prefix: str = PROVIDER_EXTERNAL_ID_PREFIX):
    return (
        select(
            PriceHistory.asset_id,
            PriceHistory.price,
            PriceHistory.captured_at,
            func.row_number()
            .over(partition_by=PriceHistory.asset_id, order_by=PriceHistory.captured_at.desc())
            .label("price_rank"),
        )
        .join(Asset, Asset.id == PriceHistory.asset_id)
        .where(source_filter)
        .where(Asset.external_id.like(asset_like_prefix))
        .subquery()
    )


def _tracked_real_rows_with_lag_subquery(source_filter, asset_like_prefix: str = PROVIDER_EXTERNAL_ID_PREFIX):
    return (
        select(
            PriceHistory.asset_id,
            Asset.name,
            Asset.external_id,
            PriceHistory.price,
            PriceHistory.captured_at,
            func.lag(PriceHistory.price)
            .over(partition_by=PriceHistory.asset_id, order_by=PriceHistory.captured_at.asc())
            .label("previous_price"),
        )
        .join(Asset, Asset.id == PriceHistory.asset_id)
        .where(source_filter)
        .where(Asset.external_id.like(asset_like_prefix))
        .subquery()
    )


def _build_health_snapshot_payload(
    db: Session,
    *,
    source_filter,
    asset_like_prefix: str = PROVIDER_EXTERNAL_ID_PREFIX,
    low_coverage_limit: int = 10,
) -> dict[str, object]:
    per_asset_counts = _real_history_counts_subquery(source_filter, asset_like_prefix)
    rows_with_lag = _tracked_real_rows_with_lag_subquery(source_filter, asset_like_prefix)
    tracked_assets = select(Asset.id).where(Asset.external_id.like(asset_like_prefix)).subquery()
    total_assets = int(db.scalar(select(func.count()).select_from(tracked_assets)) or 0)
    assets_with_real_history = int(
        db.scalar(select(func.count()).select_from(per_asset_counts)) or 0
    )
    assets_without_real_history = max(total_assets - assets_with_real_history, 0)

    average_points = db.scalar(
        select(func.avg(func.coalesce(per_asset_counts.c.real_history_points, 0)))
        .select_from(tracked_assets)
        .outerjoin(per_asset_counts, per_asset_counts.c.asset_id == tracked_assets.c.id)
    )
    average_real_history_points_per_asset = (
        Decimal(str(average_points)).quantize(Decimal("0.01"))
        if average_points is not None
        else Decimal("0.00")
    )

    assets_with_fewer_than_3_real_points = int(
        db.scalar(
            select(func.count())
            .select_from(tracked_assets)
            .outerjoin(per_asset_counts, per_asset_counts.c.asset_id == tracked_assets.c.id)
            .where(func.coalesce(per_asset_counts.c.real_history_points, 0) < 3)
        )
        or 0
    )
    assets_with_fewer_than_5_real_points = int(
        db.scalar(
            select(func.count())
            .select_from(tracked_assets)
            .outerjoin(per_asset_counts, per_asset_counts.c.asset_id == tracked_assets.c.id)
            .where(func.coalesce(per_asset_counts.c.real_history_points, 0) < 5)
        )
        or 0
    )
    assets_with_fewer_than_8_real_points = int(
        db.scalar(
            select(func.count())
            .select_from(tracked_assets)
            .outerjoin(per_asset_counts, per_asset_counts.c.asset_id == tracked_assets.c.id)
            .where(func.coalesce(per_asset_counts.c.real_history_points, 0) < 8)
        )
        or 0
    )

    cutoff_24h = datetime.now(UTC) - timedelta(hours=24)
    cutoff_7d = datetime.now(UTC) - timedelta(days=7)
    recent_real_price_rows_last_24h = int(
        db.scalar(
            select(func.count(PriceHistory.id))
            .join(Asset, Asset.id == PriceHistory.asset_id)
            .where(
                Asset.external_id.like(asset_like_prefix),
                source_filter,
                PriceHistory.captured_at >= cutoff_24h,
            )
        )
        or 0
    )
    recent_real_price_rows_last_7d = int(
        db.scalar(
            select(func.count(PriceHistory.id))
            .join(Asset, Asset.id == PriceHistory.asset_id)
            .where(
                Asset.external_id.like(asset_like_prefix),
                source_filter,
                PriceHistory.captured_at >= cutoff_7d,
            )
        )
        or 0
    )

    changed_row_condition = (
        rows_with_lag.c.previous_price.is_not(None)
        & (rows_with_lag.c.price != rows_with_lag.c.previous_price)
    )
    comparable_row_condition = rows_with_lag.c.previous_price.is_not(None)

    recent_comparable_rows_last_24h = int(
        db.scalar(
            select(func.count())
            .select_from(rows_with_lag)
            .where(
                rows_with_lag.c.captured_at >= cutoff_24h,
                comparable_row_condition,
            )
        )
        or 0
    )
    recent_rows_with_price_change_last_24h = int(
        db.scalar(
            select(func.count())
            .select_from(rows_with_lag)
            .where(
                rows_with_lag.c.captured_at >= cutoff_24h,
                changed_row_condition,
            )
        )
        or 0
    )
    recent_comparable_rows_last_7d = int(
        db.scalar(
            select(func.count())
            .select_from(rows_with_lag)
            .where(
                rows_with_lag.c.captured_at >= cutoff_7d,
                comparable_row_condition,
            )
        )
        or 0
    )
    recent_rows_with_price_change_last_7d = int(
        db.scalar(
            select(func.count())
            .select_from(rows_with_lag)
            .where(
                rows_with_lag.c.captured_at >= cutoff_7d,
                changed_row_condition,
            )
        )
        or 0
    )

    assets_with_price_change_last_24h = int(
        db.scalar(
            select(func.count())
            .select_from(
                select(rows_with_lag.c.asset_id)
                .where(
                    rows_with_lag.c.captured_at >= cutoff_24h,
                    changed_row_condition,
                )
                .distinct()
                .subquery()
            )
        )
        or 0
    )
    assets_with_price_change_last_7d = int(
        db.scalar(
            select(func.count())
            .select_from(
                select(rows_with_lag.c.asset_id)
                .where(
                    rows_with_lag.c.captured_at >= cutoff_7d,
                    changed_row_condition,
                )
                .distinct()
                .subquery()
            )
        )
        or 0
    )

    per_asset_movement = (
        select(
            rows_with_lag.c.asset_id,
            func.sum(
                case(
                    (
                        (rows_with_lag.c.captured_at >= cutoff_24h) & changed_row_condition,
                        1,
                    ),
                    else_=0,
                )
            ).label("changed_rows_last_24h"),
            func.sum(
                case(
                    (
                        (rows_with_lag.c.captured_at >= cutoff_7d) & changed_row_condition,
                        1,
                    ),
                    else_=0,
                )
            ).label("changed_rows_last_7d"),
            func.sum(
                case(
                    (rows_with_lag.c.captured_at >= cutoff_7d, 1),
                    else_=0,
                )
            ).label("rows_last_7d"),
            func.count(func.distinct(rows_with_lag.c.price)).label("distinct_real_prices"),
            func.max(rows_with_lag.c.captured_at).label("latest_captured_at"),
        )
        .group_by(rows_with_lag.c.asset_id)
        .subquery()
    )

    assets_with_no_price_movement_full_history = int(
        db.scalar(
            select(func.count())
            .select_from(per_asset_movement)
            .where(per_asset_movement.c.distinct_real_prices <= 1)
        )
        or 0
    )

    ranked = _latest_two_ranked_subquery(source_filter, asset_like_prefix)
    latest = select(ranked).where(ranked.c.price_rank == 1).subquery("latest")
    previous = select(ranked).where(ranked.c.price_rank == 2).subquery("previous")

    unchanged_latest_match = latest.join(previous, latest.c.asset_id == previous.c.asset_id)
    assets_with_unchanged_latest_price = int(
        db.scalar(
            select(func.count())
            .select_from(unchanged_latest_match)
            .where(latest.c.price == previous.c.price)
        )
        or 0
    )

    low_coverage_rows = db.execute(
        select(
            Asset.name,
            Asset.external_id,
            func.coalesce(per_asset_counts.c.real_history_points, 0).label("real_history_points"),
            per_asset_counts.c.latest_captured_at,
        )
        .outerjoin(per_asset_counts, per_asset_counts.c.asset_id == Asset.id)
        .where(Asset.external_id.like(asset_like_prefix))
        .where(func.coalesce(per_asset_counts.c.real_history_points, 0) < 8)
        .order_by(
            func.coalesce(per_asset_counts.c.real_history_points, 0).asc(),
            per_asset_counts.c.latest_captured_at.asc(),
            Asset.name.asc(),
        )
        .limit(low_coverage_limit)
    ).all()

    unchanged_latest_assets = db.execute(
        select(Asset.name)
        .join(latest, latest.c.asset_id == Asset.id)
        .join(previous, previous.c.asset_id == Asset.id)
        .where(latest.c.price == previous.c.price)
        .order_by(Asset.name.asc())
        .limit(low_coverage_limit)
    ).scalars().all()

    high_activity_rows = db.execute(
        select(
            Asset.name,
            Asset.external_id,
            per_asset_movement.c.changed_rows_last_24h,
            per_asset_movement.c.changed_rows_last_7d,
            per_asset_movement.c.rows_last_7d,
            per_asset_movement.c.distinct_real_prices,
            per_asset_movement.c.latest_captured_at,
        )
        .join(per_asset_movement, per_asset_movement.c.asset_id == Asset.id)
        .where(per_asset_movement.c.changed_rows_last_7d > 0)
        .order_by(
            per_asset_movement.c.changed_rows_last_7d.desc(),
            per_asset_movement.c.changed_rows_last_24h.desc(),
            per_asset_movement.c.distinct_real_prices.desc(),
            Asset.name.asc(),
        )
        .limit(low_coverage_limit)
    ).all()

    low_activity_rows = db.execute(
        select(
            Asset.name,
            Asset.external_id,
            per_asset_movement.c.changed_rows_last_24h,
            per_asset_movement.c.changed_rows_last_7d,
            per_asset_movement.c.rows_last_7d,
            per_asset_movement.c.distinct_real_prices,
            per_asset_movement.c.latest_captured_at,
        )
        .join(per_asset_movement, per_asset_movement.c.asset_id == Asset.id)
        .where(per_asset_movement.c.changed_rows_last_7d == 0)
        .order_by(
            per_asset_movement.c.rows_last_7d.desc(),
            per_asset_movement.c.distinct_real_prices.asc(),
            Asset.name.asc(),
        )
        .limit(low_coverage_limit)
    ).all()

    percent_recent_rows_changed_last_24h = (
        _quantize_decimal((recent_rows_with_price_change_last_24h / recent_comparable_rows_last_24h) * 100)
        if recent_comparable_rows_last_24h
        else Decimal("0.00")
    )
    percent_recent_rows_changed_last_7d = (
        _quantize_decimal((recent_rows_with_price_change_last_7d / recent_comparable_rows_last_7d) * 100)
        if recent_comparable_rows_last_7d
        else Decimal("0.00")
    )

    average_recent_rows_per_asset_last_24h = (
        _quantize_decimal(recent_real_price_rows_last_24h / assets_with_real_history)
        if assets_with_real_history
        else Decimal("0.00")
    )
    average_recent_rows_per_asset_last_7d = (
        _quantize_decimal(recent_real_price_rows_last_7d / assets_with_real_history)
        if assets_with_real_history
        else Decimal("0.00")
    )
    average_changed_rows_per_asset_last_24h = (
        _quantize_decimal(recent_rows_with_price_change_last_24h / assets_with_real_history)
        if assets_with_real_history
        else Decimal("0.00")
    )
    average_changed_rows_per_asset_last_7d = (
        _quantize_decimal(recent_rows_with_price_change_last_7d / assets_with_real_history)
        if assets_with_real_history
        else Decimal("0.00")
    )
    rows_per_recent_price_change_last_24h = (
        _quantize_decimal(recent_comparable_rows_last_24h / recent_rows_with_price_change_last_24h)
        if recent_rows_with_price_change_last_24h
        else None
    )
    rows_per_recent_price_change_last_7d = (
        _quantize_decimal(recent_comparable_rows_last_7d / recent_rows_with_price_change_last_7d)
        if recent_rows_with_price_change_last_7d
        else None
    )

    return {
        "total_assets": total_assets,
        "assets_with_real_history": assets_with_real_history,
        "assets_without_real_history": assets_without_real_history,
        "average_real_history_points_per_asset": average_real_history_points_per_asset,
        "assets_with_fewer_than_3_real_points": assets_with_fewer_than_3_real_points,
        "assets_with_fewer_than_5_real_points": assets_with_fewer_than_5_real_points,
        "assets_with_fewer_than_8_real_points": assets_with_fewer_than_8_real_points,
        "recent_real_price_rows_last_24h": recent_real_price_rows_last_24h,
        "recent_real_price_rows_last_7d": recent_real_price_rows_last_7d,
        "recent_comparable_rows_last_24h": recent_comparable_rows_last_24h,
        "recent_rows_with_price_change_last_24h": recent_rows_with_price_change_last_24h,
        "percent_recent_rows_changed_last_24h": percent_recent_rows_changed_last_24h,
        "recent_comparable_rows_last_7d": recent_comparable_rows_last_7d,
        "recent_rows_with_price_change_last_7d": recent_rows_with_price_change_last_7d,
        "percent_recent_rows_changed_last_7d": percent_recent_rows_changed_last_7d,
        "assets_with_price_change_last_24h": assets_with_price_change_last_24h,
        "assets_with_price_change_last_7d": assets_with_price_change_last_7d,
        "assets_with_no_price_movement_full_history": assets_with_no_price_movement_full_history,
        "assets_with_unchanged_latest_price": assets_with_unchanged_latest_price,
        "average_recent_rows_per_asset_last_24h": average_recent_rows_per_asset_last_24h,
        "average_recent_rows_per_asset_last_7d": average_recent_rows_per_asset_last_7d,
        "average_changed_rows_per_asset_last_24h": average_changed_rows_per_asset_last_24h,
        "average_changed_rows_per_asset_last_7d": average_changed_rows_per_asset_last_7d,
        "rows_per_recent_price_change_last_24h": rows_per_recent_price_change_last_24h,
        "rows_per_recent_price_change_last_7d": rows_per_recent_price_change_last_7d,
        "low_coverage_assets": [
            AssetCoverageSnapshot(
                name=name,
                external_id=external_id,
                real_history_points=int(real_history_points),
                latest_captured_at=latest_captured_at,
            )
            for name, external_id, real_history_points, latest_captured_at in low_coverage_rows
        ],
        "unchanged_latest_assets": list(unchanged_latest_assets),
        "high_activity_assets": [
            AssetMovementSnapshot(
                name=name,
                external_id=external_id,
                changed_rows_last_24h=int(changed_rows_last_24h or 0),
                changed_rows_last_7d=int(changed_rows_last_7d or 0),
                rows_last_7d=int(rows_last_7d or 0),
                distinct_real_prices=int(distinct_real_prices or 0),
                latest_captured_at=latest_captured_at,
            )
            for (
                name,
                external_id,
                changed_rows_last_24h,
                changed_rows_last_7d,
                rows_last_7d,
                distinct_real_prices,
                latest_captured_at,
            ) in high_activity_rows
        ],
        "low_activity_assets": [
            AssetMovementSnapshot(
                name=name,
                external_id=external_id,
                changed_rows_last_24h=int(changed_rows_last_24h or 0),
                changed_rows_last_7d=int(changed_rows_last_7d or 0),
                rows_last_7d=int(rows_last_7d or 0),
                distinct_real_prices=int(distinct_real_prices or 0),
                latest_captured_at=latest_captured_at,
            )
            for (
                name,
                external_id,
                changed_rows_last_24h,
                changed_rows_last_7d,
                rows_last_7d,
                distinct_real_prices,
                latest_captured_at,
            ) in low_activity_rows
        ],
    }


def _build_pool_health_snapshot(
    db: Session,
    *,
    key: str,
    label: str,
    asset_prefix_like: str,
    source_filter,
    low_coverage_limit: int = 10,
) -> PoolHealthSnapshot:
    payload = _build_health_snapshot_payload(
        db,
        source_filter=source_filter,
        asset_like_prefix=asset_prefix_like,
        low_coverage_limit=low_coverage_limit,
    )
    return PoolHealthSnapshot(
        key=key,
        label=label,
        asset_prefix_like=asset_prefix_like,
        **payload,
    )


def _build_provider_health_snapshot(
    db: Session,
    *,
    slot: str,
    source: str,
    label: str,
    is_primary: bool,
    low_coverage_limit: int = 10,
) -> ProviderHealthSnapshot:
    source_filter = PriceHistory.source == source
    payload = _build_health_snapshot_payload(
        db,
        source_filter=source_filter,
        low_coverage_limit=low_coverage_limit,
    )
    pool_reports = [
        _build_pool_health_snapshot(
            db,
            key=pool.key,
            label=pool.label,
            asset_prefix_like=pool.external_id_like,
            source_filter=source_filter,
            low_coverage_limit=low_coverage_limit,
        )
        for pool in get_tracked_pokemon_pools()
    ]
    return ProviderHealthSnapshot(
        slot=slot,
        source=source,
        label=label,
        is_primary=is_primary,
        pool_reports=pool_reports,
        tag_reports=_build_tag_health_snapshots(
            db,
            source_filter=source_filter,
            low_coverage_limit=low_coverage_limit,
        ),
        **payload,
    )


def _collect_asset_tag_metric_records(
    db: Session,
    *,
    source_filter,
    asset_like_prefix: str = PROVIDER_EXTERNAL_ID_PREFIX,
) -> list[_AssetTagMetricRecord]:
    tracked_assets = db.execute(
        select(Asset)
        .where(Asset.external_id.like(asset_like_prefix))
        .order_by(Asset.name.asc(), Asset.external_id.asc())
    ).scalars().all()
    if not tracked_assets:
        return []

    history_rows = db.execute(
        select(
            PriceHistory.asset_id,
            PriceHistory.price,
            PriceHistory.captured_at,
        )
        .join(Asset, Asset.id == PriceHistory.asset_id)
        .where(
            source_filter,
            Asset.external_id.like(asset_like_prefix),
        )
        .order_by(PriceHistory.asset_id.asc(), PriceHistory.captured_at.asc())
    ).all()

    prices_by_asset: dict = {}
    for asset_id, price, captured_at in history_rows:
        prices_by_asset.setdefault(asset_id, []).append((price, _coerce_datetime_to_utc(captured_at)))

    cutoff_24h = datetime.now(UTC) - timedelta(hours=24)
    cutoff_7d = datetime.now(UTC) - timedelta(days=7)
    records: list[_AssetTagMetricRecord] = []
    for asset in tracked_assets:
        rows = prices_by_asset.get(asset.id, [])
        recent_real_rows_last_24h = 0
        recent_real_rows_last_7d = 0
        recent_comparable_rows_last_24h = 0
        recent_rows_with_price_change_last_24h = 0
        recent_comparable_rows_last_7d = 0
        recent_rows_with_price_change_last_7d = 0
        previous_price = None

        for price, captured_at in rows:
            if captured_at >= cutoff_24h:
                recent_real_rows_last_24h += 1
            if captured_at >= cutoff_7d:
                recent_real_rows_last_7d += 1

            if previous_price is not None:
                if captured_at >= cutoff_24h:
                    recent_comparable_rows_last_24h += 1
                    if price != previous_price:
                        recent_rows_with_price_change_last_24h += 1
                if captured_at >= cutoff_7d:
                    recent_comparable_rows_last_7d += 1
                    if price != previous_price:
                        recent_rows_with_price_change_last_7d += 1

            previous_price = price

        latest_captured_at = rows[-1][1] if rows else None
        latest_two_prices_unchanged = len(rows) >= 2 and rows[-1][0] == rows[-2][0]
        distinct_real_prices = len({str(price) for price, _ in rows})
        records.append(
            _AssetTagMetricRecord(
                asset=asset,
                history_points=len(rows),
                latest_captured_at=latest_captured_at,
                recent_real_rows_last_24h=recent_real_rows_last_24h,
                recent_real_rows_last_7d=recent_real_rows_last_7d,
                recent_comparable_rows_last_24h=recent_comparable_rows_last_24h,
                recent_rows_with_price_change_last_24h=recent_rows_with_price_change_last_24h,
                recent_comparable_rows_last_7d=recent_comparable_rows_last_7d,
                recent_rows_with_price_change_last_7d=recent_rows_with_price_change_last_7d,
                distinct_real_prices=distinct_real_prices,
                latest_two_prices_unchanged=latest_two_prices_unchanged,
            )
        )
    return records


def _build_tag_health_snapshot(
    *,
    dimension: str,
    tag_value: str,
    records: list[_AssetTagMetricRecord],
) -> TagHealthSnapshot:
    total_assets = len(records)
    assets_with_real_history = sum(1 for record in records if record.history_points > 0)
    average_real_history_points_per_asset = (
        _quantize_decimal(sum(record.history_points for record in records) / total_assets)
        if total_assets
        else Decimal("0.00")
    )
    assets_with_price_change_last_24h = sum(
        1 for record in records if record.recent_rows_with_price_change_last_24h > 0
    )
    assets_with_price_change_last_7d = sum(
        1 for record in records if record.recent_rows_with_price_change_last_7d > 0
    )
    recent_comparable_rows_last_24h = sum(
        record.recent_comparable_rows_last_24h for record in records
    )
    recent_rows_with_price_change_last_24h = sum(
        record.recent_rows_with_price_change_last_24h for record in records
    )
    recent_comparable_rows_last_7d = sum(
        record.recent_comparable_rows_last_7d for record in records
    )
    recent_rows_with_price_change_last_7d = sum(
        record.recent_rows_with_price_change_last_7d for record in records
    )
    percent_recent_rows_changed_last_24h = (
        _quantize_decimal(
            (recent_rows_with_price_change_last_24h / recent_comparable_rows_last_24h) * 100
        )
        if recent_comparable_rows_last_24h
        else Decimal("0.00")
    )
    percent_recent_rows_changed_last_7d = (
        _quantize_decimal(
            (recent_rows_with_price_change_last_7d / recent_comparable_rows_last_7d) * 100
        )
        if recent_comparable_rows_last_7d
        else Decimal("0.00")
    )
    assets_with_no_price_movement_full_history = sum(
        1
        for record in records
        if record.history_points > 0 and record.distinct_real_prices <= 1
    )
    assets_with_unchanged_latest_price = sum(
        1 for record in records if record.latest_two_prices_unchanged
    )
    return TagHealthSnapshot(
        dimension=dimension,
        dimension_label=TAG_DIMENSION_LABELS.get(dimension, dimension.replace("_", " ").title()),
        tag_value=tag_value,
        total_assets=total_assets,
        assets_with_real_history=assets_with_real_history,
        average_real_history_points_per_asset=average_real_history_points_per_asset,
        assets_with_price_change_last_24h=assets_with_price_change_last_24h,
        assets_with_price_change_last_7d=assets_with_price_change_last_7d,
        recent_comparable_rows_last_24h=recent_comparable_rows_last_24h,
        recent_rows_with_price_change_last_24h=recent_rows_with_price_change_last_24h,
        percent_recent_rows_changed_last_24h=percent_recent_rows_changed_last_24h,
        recent_comparable_rows_last_7d=recent_comparable_rows_last_7d,
        recent_rows_with_price_change_last_7d=recent_rows_with_price_change_last_7d,
        percent_recent_rows_changed_last_7d=percent_recent_rows_changed_last_7d,
        assets_with_no_price_movement_full_history=assets_with_no_price_movement_full_history,
        assets_with_unchanged_latest_price=assets_with_unchanged_latest_price,
    )


def _build_tag_health_snapshots(
    db: Session,
    *,
    source_filter,
    asset_like_prefix: str = PROVIDER_EXTERNAL_ID_PREFIX,
    low_coverage_limit: int = 10,
) -> list[TagHealthSnapshot]:
    del low_coverage_limit
    records = _collect_asset_tag_metric_records(
        db,
        source_filter=source_filter,
        asset_like_prefix=asset_like_prefix,
    )
    if not records:
        return []

    grouped_records: dict[tuple[str, str], list[_AssetTagMetricRecord]] = {}
    for record in records:
        for dimension, tag_value in get_asset_tag_values(record.asset).items():
            grouped_records.setdefault((dimension, tag_value), []).append(record)

    snapshots: list[TagHealthSnapshot] = []
    dimensions_in_order = list(TAG_DIMENSION_ORDER)
    remaining_dimensions = sorted(
        {dimension for dimension, _ in grouped_records} - set(TAG_DIMENSION_ORDER)
    )
    for dimension in [*dimensions_in_order, *remaining_dimensions]:
        tag_values = sorted(
            [tag_value for grouped_dimension, tag_value in grouped_records if grouped_dimension == dimension],
            key=lambda value: get_tag_value_sort_key(dimension, value),
        )
        for tag_value in tag_values:
            snapshots.append(
                _build_tag_health_snapshot(
                    dimension=dimension,
                    tag_value=tag_value,
                    records=grouped_records[(dimension, tag_value)],
                )
            )
    return snapshots


def _quantize_decimal(value: Decimal | float | int | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"))


def get_data_health_report(db: Session, *, low_coverage_limit: int = 10) -> DataHealthReport:
    source_filter = get_active_price_source_filter(db)
    payload = _build_health_snapshot_payload(
        db,
        source_filter=source_filter,
        low_coverage_limit=low_coverage_limit,
    )
    pool_reports = [
        _build_pool_health_snapshot(
            db,
            key=pool.key,
            label=pool.label,
            asset_prefix_like=pool.external_id_like,
            source_filter=source_filter,
            low_coverage_limit=low_coverage_limit,
        )
        for pool in get_tracked_pokemon_pools()
    ]
    tag_reports = _build_tag_health_snapshots(
        db,
        source_filter=source_filter,
        low_coverage_limit=low_coverage_limit,
    )
    provider_reports = [
        _build_provider_health_snapshot(
            db,
            slot=provider.slot,
            source=provider.source,
            label=provider.label,
            is_primary=provider.is_primary,
            low_coverage_limit=low_coverage_limit,
        )
        for provider in get_configured_price_providers()
    ]

    return DataHealthReport(
        pool_reports=pool_reports,
        tag_reports=tag_reports,
        provider_reports=provider_reports,
        **payload,
    )
