from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.price_sources import SAMPLE_PRICE_SOURCE, get_active_price_source_filter, get_primary_price_source
from backend.app.models.asset import Asset
from backend.app.models.asset_signal import AssetSignal
from backend.app.models.price_history import PriceHistory
from backend.app.schemas.market import (
    MarketIndexResponse,
    MarketOverviewResponse,
    MarketSignalSummaryResponse,
    MarketTopMoverResponse,
)

RAW_MARKET_SEGMENT = "raw"
DECIMAL_PLACES = Decimal("0.01")


@dataclass(frozen=True)
class AssetMovement:
    asset_id: object
    name: str
    game: str
    set_name: str | None
    latest_price: Decimal
    previous_price: Decimal
    absolute_change: Decimal
    percent_change: Decimal


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(DECIMAL_PLACES)


def _direction(change_pct: Decimal) -> str:
    if change_pct > 0:
        return "up"
    if change_pct < 0:
        return "down"
    return "flat"


def _confidence_label(observed_assets: int) -> str:
    if observed_assets >= 10:
        return "high"
    if observed_assets >= 3:
        return "medium"
    if observed_assets >= 1:
        return "low"
    return "insufficient"


def _market_sentiment(asset_movements: list[AssetMovement]) -> str:
    if not asset_movements:
        return "insufficient_data"
    average_change = sum((item.percent_change for item in asset_movements), Decimal("0")) / Decimal(
        len(asset_movements)
    )
    if average_change >= Decimal("1.00"):
        return "bullish"
    if average_change <= Decimal("-1.00"):
        return "bearish"
    return "neutral"


def _label_for_game(game: str) -> str:
    custom_labels = {
        "pokemon": "Pokemon Market",
        "yugioh": "Yu-Gi-Oh Market",
    }
    return custom_labels.get(game, f"{game.replace('_', ' ').title()} Market")


def _active_source_name(db: Session) -> str:
    primary_source = get_primary_price_source()
    has_primary_rows = (
        db.scalar(select(PriceHistory.id).where(PriceHistory.source == primary_source).limit(1))
        is not None
    )
    return primary_source if has_primary_rows else SAMPLE_PRICE_SOURCE


def _rank_alias(ranked, alias_name: str, rank: int):
    return select(ranked).where(ranked.c.price_rank == rank).subquery(alias_name)


def _build_price_rank_subquery(db: Session):
    source_filter = get_active_price_source_filter(db)
    return (
        select(
            PriceHistory.asset_id,
            PriceHistory.price,
            PriceHistory.captured_at,
            func.row_number()
            .over(partition_by=PriceHistory.asset_id, order_by=PriceHistory.captured_at.desc())
            .label("price_rank"),
        )
        .where(source_filter, PriceHistory.market_segment == RAW_MARKET_SEGMENT)
        .subquery()
    )


def _get_current_asset_counts(db: Session, current_price) -> dict[str, int]:
    rows = db.execute(
        select(Asset.game, func.count(Asset.id))
        .join(current_price, current_price.c.asset_id == Asset.id)
        .group_by(Asset.game)
    ).all()
    return {row.game: int(row[1]) for row in rows}


def _get_asset_movements(db: Session, current_price, previous_price) -> list[AssetMovement]:
    rows = db.execute(
        select(
            Asset.id,
            Asset.name,
            Asset.game,
            Asset.set_name,
            current_price.c.price.label("latest_price"),
            previous_price.c.price.label("previous_price"),
        )
        .join(current_price, current_price.c.asset_id == Asset.id)
        .join(previous_price, previous_price.c.asset_id == Asset.id)
    ).all()

    movements: list[AssetMovement] = []
    for row in rows:
        previous = Decimal(row.previous_price)
        if previous == 0:
            continue
        latest = Decimal(row.latest_price)
        absolute_change = latest - previous
        percent_change = (absolute_change / previous) * Decimal("100")
        movements.append(
            AssetMovement(
                asset_id=row.id,
                name=row.name,
                game=row.game,
                set_name=row.set_name,
                latest_price=_quantize(latest),
                previous_price=_quantize(previous),
                absolute_change=_quantize(absolute_change),
                percent_change=_quantize(percent_change),
            )
        )
    return movements


def _build_indexes(
    asset_movements: list[AssetMovement],
    current_asset_counts: dict[str, int],
) -> list[MarketIndexResponse]:
    grouped: dict[str, list[AssetMovement]] = defaultdict(list)
    for movement in asset_movements:
        grouped[movement.game].append(movement)

    indexes: list[MarketIndexResponse] = []
    for game, movements in grouped.items():
        change_pct = sum((item.percent_change for item in movements), Decimal("0")) / Decimal(len(movements))
        indexes.append(
            MarketIndexResponse(
                game=game,
                label=_label_for_game(game),
                change_pct=_quantize(change_pct),
                direction=_direction(change_pct),
                observed_assets=len(movements),
                current_assets=current_asset_counts.get(game, 0),
                confidence_label=_confidence_label(len(movements)),
            )
        )

    indexes.sort(key=lambda item: (-item.observed_assets, item.game))
    return indexes


def _build_top_movers(
    asset_movements: list[AssetMovement],
    *,
    limit: int,
) -> list[MarketTopMoverResponse]:
    sorted_movements = sorted(
        asset_movements,
        key=lambda item: (-abs(item.percent_change), item.name),
    )
    return [
        MarketTopMoverResponse(
            asset_id=movement.asset_id,
            name=movement.name,
            game=movement.game,
            set_name=movement.set_name,
            latest_price=movement.latest_price,
            previous_price=movement.previous_price,
            percent_change=movement.percent_change,
            absolute_change=movement.absolute_change,
            direction=_direction(movement.percent_change),
        )
        for movement in sorted_movements[:limit]
    ]


def _build_signal_summary(db: Session) -> list[MarketSignalSummaryResponse]:
    rows = db.execute(
        select(
            AssetSignal.label,
            func.count(AssetSignal.id).label("count"),
            func.avg(AssetSignal.confidence).label("average_confidence"),
        )
        .group_by(AssetSignal.label)
        .order_by(func.count(AssetSignal.id).desc(), AssetSignal.label.asc())
    ).all()
    return [
        MarketSignalSummaryResponse(
            label=row.label,
            count=int(row.count),
            average_confidence=(
                _quantize(Decimal(str(row.average_confidence)))
                if row.average_confidence is not None
                else None
            ),
        )
        for row in rows
    ]


def _build_commentary(
    *,
    market_sentiment: str,
    indexes: list[MarketIndexResponse],
    top_movers: list[MarketTopMoverResponse],
    signal_summary: list[MarketSignalSummaryResponse],
    observed_asset_count: int,
) -> str:
    if market_sentiment == "insufficient_data":
        return (
            "Insufficient evidence to summarize today's market. "
            "The overview needs at least two raw price observations for one asset from the active price source."
        )

    strongest_index = indexes[0]
    commentary = (
        f"Market is {market_sentiment} based on {observed_asset_count} raw price series "
        f"across {len(indexes)} game market(s). "
        f"{strongest_index.label} is {strongest_index.direction} {strongest_index.change_pct}% "
        f"from comparable raw observations."
    )
    if top_movers:
        top = top_movers[0]
        commentary += f" The largest observed move is {top.name} at {top.percent_change:+}%."
    if signal_summary:
        signal_total = sum(item.count for item in signal_summary)
        commentary += f" The signal feed currently contains {signal_total} active signal(s)."
    commentary += " This is a rule-based evidence summary, not an AI recommendation."
    return commentary


def get_market_overview(db: Session, *, mover_limit: int = 10) -> MarketOverviewResponse:
    active_source = _active_source_name(db)
    ranked = _build_price_rank_subquery(db)
    current_price = _rank_alias(ranked, "market_overview_current_price", 1)
    previous_price = _rank_alias(ranked, "market_overview_previous_price", 2)

    current_asset_counts = _get_current_asset_counts(db, current_price)
    asset_movements = _get_asset_movements(db, current_price, previous_price)

    if not asset_movements:
        return MarketOverviewResponse(
            generated_at=datetime.now(UTC),
            market_sentiment="insufficient_data",
            confidence_label="insufficient",
            indexes=[],
            top_movers=[],
            signal_summary=[],
            commentary=_build_commentary(
                market_sentiment="insufficient_data",
                indexes=[],
                top_movers=[],
                signal_summary=[],
                observed_asset_count=0,
            ),
            evidence=[
                "market_segment=raw",
                f"active price source: {active_source}",
                "0 comparable raw price series",
            ],
        )

    indexes = _build_indexes(asset_movements, current_asset_counts)
    top_movers = _build_top_movers(asset_movements, limit=mover_limit)
    signal_summary = _build_signal_summary(db)
    sentiment = _market_sentiment(asset_movements)

    return MarketOverviewResponse(
        generated_at=datetime.now(UTC),
        market_sentiment=sentiment,
        confidence_label=_confidence_label(len(asset_movements)),
        indexes=indexes,
        top_movers=top_movers,
        signal_summary=signal_summary,
        commentary=_build_commentary(
            market_sentiment=sentiment,
            indexes=indexes,
            top_movers=top_movers,
            signal_summary=signal_summary,
            observed_asset_count=len(asset_movements),
        ),
        evidence=[
            "market_segment=raw",
            f"active price source: {active_source}",
            f"{len(asset_movements)} comparable raw price series",
            f"{len(indexes)} game market summaries",
        ],
    )
