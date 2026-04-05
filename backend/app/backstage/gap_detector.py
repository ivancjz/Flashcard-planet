from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory

DEFAULT_SET_COVERAGE_THRESHOLD = 0.50


@dataclass(frozen=True)
class AssetHistoryCoverageRow:
    asset_id: UUID
    asset_name: str
    set_id: str | None
    set_name: str | None
    history_count: int


@dataclass(frozen=True)
class GapQueueEntry:
    item_type: str
    gap_type: str
    priority: int
    asset_id: UUID | None = None
    asset_name: str | None = None
    set_id: str | None = None
    set_name: str | None = None
    history_count: int | None = None
    required_history_count: int | None = None
    covered_cards: int | None = None
    total_cards: int | None = None
    coverage_ratio: float | None = None


@dataclass(frozen=True)
class GapReport:
    generated_at: datetime
    history_threshold: int
    set_coverage_threshold: float
    total_assets: int
    covered_assets: int
    assets_with_any_history: int
    zero_history_assets: int
    thin_history_assets: int
    partial_sets: int
    gap_count: int
    priority_queue: list[GapQueueEntry] = field(default_factory=list)


@dataclass
class _SetCoverageAccumulator:
    set_id: str | None
    set_name: str | None
    total_cards: int = 0
    covered_cards: int = 0


def _normalize_thresholds(
    history_threshold: int,
    set_coverage_threshold: float,
) -> tuple[int, float]:
    if history_threshold < 1:
        raise ValueError("history_threshold must be at least 1.")
    if not 0 < set_coverage_threshold <= 1:
        raise ValueError("set_coverage_threshold must be between 0 and 1.")
    return history_threshold, set_coverage_threshold


def fetch_asset_history_coverage_rows(db: Session) -> list[AssetHistoryCoverageRow]:
    per_asset_counts = (
        select(
            PriceHistory.asset_id.label("asset_id"),
            func.count(PriceHistory.id).label("history_count"),
        )
        .group_by(PriceHistory.asset_id)
        .subquery()
    )

    rows = db.execute(
        select(
            Asset,
            func.coalesce(per_asset_counts.c.history_count, 0).label("history_count"),
        )
        .outerjoin(per_asset_counts, per_asset_counts.c.asset_id == Asset.id)
        .order_by(Asset.set_name.asc(), Asset.name.asc(), Asset.id.asc())
    ).all()

    coverage_rows: list[AssetHistoryCoverageRow] = []
    for asset, history_count in rows:
        metadata = asset.metadata_json if isinstance(asset.metadata_json, dict) else {}
        coverage_rows.append(
            AssetHistoryCoverageRow(
                asset_id=asset.id,
                asset_name=asset.name,
                set_id=metadata.get("set_id"),
                set_name=asset.set_name,
                history_count=int(history_count or 0),
            )
        )
    return coverage_rows


def build_gap_report(
    asset_rows: list[AssetHistoryCoverageRow],
    *,
    history_threshold: int = 7,
    set_coverage_threshold: float = DEFAULT_SET_COVERAGE_THRESHOLD,
) -> GapReport:
    history_threshold, set_coverage_threshold = _normalize_thresholds(
        history_threshold,
        set_coverage_threshold,
    )

    zero_history_rows = sorted(
        (row for row in asset_rows if row.history_count == 0),
        key=lambda row: (row.set_name or "", row.asset_name.lower(), str(row.asset_id)),
    )
    thin_history_rows = sorted(
        (row for row in asset_rows if 0 < row.history_count < history_threshold),
        key=lambda row: (row.history_count, row.set_name or "", row.asset_name.lower(), str(row.asset_id)),
    )

    sets_by_identifier: dict[str, _SetCoverageAccumulator] = {}
    for row in asset_rows:
        set_identifier = row.set_id or row.set_name
        if not set_identifier:
            continue

        accumulator = sets_by_identifier.setdefault(
            set_identifier,
            _SetCoverageAccumulator(set_id=row.set_id, set_name=row.set_name),
        )
        accumulator.total_cards += 1
        if row.history_count >= history_threshold:
            accumulator.covered_cards += 1

    partial_set_entries = sorted(
        (
            GapQueueEntry(
                item_type="set",
                gap_type="partial_set",
                priority=3,
                set_id=accumulator.set_id or accumulator.set_name,
                set_name=accumulator.set_name,
                required_history_count=history_threshold,
                covered_cards=accumulator.covered_cards,
                total_cards=accumulator.total_cards,
                coverage_ratio=round(accumulator.covered_cards / accumulator.total_cards, 4),
            )
            for accumulator in sets_by_identifier.values()
            if accumulator.total_cards
            and (accumulator.covered_cards / accumulator.total_cards) < set_coverage_threshold
        ),
        key=lambda entry: (
            entry.coverage_ratio if entry.coverage_ratio is not None else 1,
            -(entry.total_cards or 0),
            entry.set_name or entry.set_id or "",
        ),
    )

    priority_queue = [
        GapQueueEntry(
            item_type="asset",
            gap_type="zero_history",
            priority=1,
            asset_id=row.asset_id,
            asset_name=row.asset_name,
            set_id=row.set_id,
            set_name=row.set_name,
            history_count=row.history_count,
            required_history_count=history_threshold,
        )
        for row in zero_history_rows
    ]
    priority_queue.extend(
        GapQueueEntry(
            item_type="asset",
            gap_type="thin_history",
            priority=2,
            asset_id=row.asset_id,
            asset_name=row.asset_name,
            set_id=row.set_id,
            set_name=row.set_name,
            history_count=row.history_count,
            required_history_count=history_threshold,
        )
        for row in thin_history_rows
    )
    priority_queue.extend(partial_set_entries)

    total_assets = len(asset_rows)
    covered_assets = sum(1 for row in asset_rows if row.history_count >= history_threshold)
    assets_with_any_history = sum(1 for row in asset_rows if row.history_count > 0)

    return GapReport(
        generated_at=datetime.now(UTC).replace(microsecond=0),
        history_threshold=history_threshold,
        set_coverage_threshold=set_coverage_threshold,
        total_assets=total_assets,
        covered_assets=covered_assets,
        assets_with_any_history=assets_with_any_history,
        zero_history_assets=len(zero_history_rows),
        thin_history_assets=len(thin_history_rows),
        partial_sets=len(partial_set_entries),
        gap_count=len(priority_queue),
        priority_queue=priority_queue,
    )


def get_gap_report(
    db: Session,
    *,
    history_threshold: int | None = None,
    set_coverage_threshold: float | None = None,
) -> GapReport:
    settings = get_settings()
    return build_gap_report(
        fetch_asset_history_coverage_rows(db),
        history_threshold=(
            settings.gap_history_threshold
            if history_threshold is None
            else history_threshold
        ),
        set_coverage_threshold=(
            settings.gap_set_coverage_threshold
            if set_coverage_threshold is None
            else set_coverage_threshold
        ),
    )
