from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.price_sources import POKEMON_TCG_PRICE_SOURCE, get_configured_price_providers, get_primary_price_source
from backend.app.core.tracked_pools import (
    BASE_SET_POOL_KEY,
    HIGH_ACTIVITY_TRIAL_POOL_KEY,
    PRIMARY_SMART_OBSERVATION_POOL_KEY,
    TRIAL_POOL_KEY,
)
from backend.app.ingestion.pokemon_tcg import IngestionResult
from backend.app.models.alert import Alert
from backend.app.models.observation_match_log import ObservationMatchLog
from backend.app.models.watchlist import Watchlist
from backend.app.services.data_health_service import PoolHealthSnapshot, get_data_health_report

_logger = logging.getLogger(__name__)


def _safe_block(fn, *args, block_name: str, **kwargs) -> dict:
    """Call fn(*args, **kwargs); return error dict if it raises."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        _logger.exception("Diagnostics block %r failed", block_name)
        return {"status": "error", "block": block_name, "error": str(exc)}


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).isoformat()
    return value.astimezone(UTC).isoformat()


def _format_decimal(value: Decimal | None, *, suffix: str = "") -> str:
    if value is None:
        return "N/A"
    return f"{value}{suffix}"


def _serialize_pool(pool: PoolHealthSnapshot) -> dict[str, Any]:
    return {
        "key": pool.key,
        "label": pool.label,
        "total_assets": pool.total_assets,
        "assets_with_real_history": pool.assets_with_real_history,
        "assets_without_real_history": pool.assets_without_real_history,
        "average_history_depth": _format_decimal(pool.average_real_history_points_per_asset),
        "assets_with_price_change_last_24h": pool.assets_with_price_change_last_24h,
        "assets_with_price_change_last_7d": pool.assets_with_price_change_last_7d,
        "row_change_pct_last_24h": _format_decimal(pool.percent_recent_rows_changed_last_24h, suffix="%"),
        "row_change_pct_last_7d": _format_decimal(pool.percent_recent_rows_changed_last_7d, suffix="%"),
        "assets_with_no_price_movement_full_history": pool.assets_with_no_price_movement_full_history,
        "assets_with_unchanged_latest_price": pool.assets_with_unchanged_latest_price,
    }


def _get_pool_by_key(pool_reports: list[PoolHealthSnapshot], key: str) -> PoolHealthSnapshot | None:
    return next((pool for pool in pool_reports if pool.key == key), None)


def _build_smart_pool_reference(pool_reports: list[PoolHealthSnapshot]) -> dict[str, Any]:
    focus_pool = _get_pool_by_key(pool_reports, PRIMARY_SMART_OBSERVATION_POOL_KEY)
    base_pool = _get_pool_by_key(pool_reports, BASE_SET_POOL_KEY)
    trial_pool = _get_pool_by_key(pool_reports, TRIAL_POOL_KEY)
    legacy_high_activity_pool = _get_pool_by_key(pool_reports, HIGH_ACTIVITY_TRIAL_POOL_KEY)

    if focus_pool is None:
        return {
            "key": PRIMARY_SMART_OBSERVATION_POOL_KEY,
            "label": "High-Activity v2",
            "status": "missing",
            "headline": "High-Activity v2 is not configured.",
            "summary": "Diagnostics cannot center the smart observation pool until High-Activity v2 is configured.",
            "comparison_lines": [],
            "recommendation": "Configure High-Activity v2 before the next provider-evaluation run.",
        }

    comparison_lines = [
        (
            f"Primary smart observation pool: {focus_pool.label}. "
            f"History coverage {focus_pool.assets_with_real_history}/{focus_pool.total_assets}, "
            f"7d changed assets {focus_pool.assets_with_price_change_last_7d}/{focus_pool.assets_with_real_history}, "
            f"7d row change {focus_pool.percent_recent_rows_changed_last_7d}%."
        )
    ]
    if base_pool is not None:
        comparison_lines.append(
            (
                f"Against {base_pool.label}: "
                f"v2 no-movement assets {focus_pool.assets_with_no_price_movement_full_history} "
                f"vs {base_pool.assets_with_no_price_movement_full_history}, "
                f"7d row change {focus_pool.percent_recent_rows_changed_last_7d}% "
                f"vs {base_pool.percent_recent_rows_changed_last_7d}%."
            )
        )
    if trial_pool is not None:
        comparison_lines.append(
            (
                f"Against {trial_pool.label}: "
                f"v2 no-movement assets {focus_pool.assets_with_no_price_movement_full_history} "
                f"vs {trial_pool.assets_with_no_price_movement_full_history}, "
                f"7d changed assets {focus_pool.assets_with_price_change_last_7d}/{focus_pool.assets_with_real_history} "
                f"vs {trial_pool.assets_with_price_change_last_7d}/{trial_pool.assets_with_real_history}."
            )
        )
    if legacy_high_activity_pool is not None:
        comparison_lines.append(
            (
                f"Against {legacy_high_activity_pool.label}: "
                f"v2 no-movement assets {focus_pool.assets_with_no_price_movement_full_history} "
                f"vs {legacy_high_activity_pool.assets_with_no_price_movement_full_history}, "
                f"7d row change {focus_pool.percent_recent_rows_changed_last_7d}% "
                f"vs {legacy_high_activity_pool.percent_recent_rows_changed_last_7d}%."
            )
        )

    return {
        "key": focus_pool.key,
        "label": focus_pool.label,
        "status": "active",
        "headline": "High-Activity v2 is the main smart observation reference.",
        "summary": (
            "Old pools remain available for comparison, but the current-provider evaluation should center "
            "on High-Activity v2 when deciding whether weak smart-pool results come from selection or coverage."
        ),
        "comparison_lines": comparison_lines,
        "recommendation": (
            "Keep the current provider, keep High-Activity v2 as the smart observation pool, "
            "and use the legacy pools only as comparison baselines."
        ),
    }


def _build_recent_observation_stage(
    db: Session,
    *,
    provider: str,
    recent_observation_limit: int,
) -> dict[str, Any]:
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    grouped_rows = db.execute(
        select(
            ObservationMatchLog.match_status,
            func.count(ObservationMatchLog.id),
        )
        .where(
            ObservationMatchLog.provider == provider,
            ObservationMatchLog.created_at >= cutoff,
        )
        .group_by(ObservationMatchLog.match_status)
    ).all()
    match_status_counts = {
        match_status: int(count)
        for match_status, count in grouped_rows
    }
    review_logs = db.execute(
        select(ObservationMatchLog)
        .where(
            ObservationMatchLog.provider == provider,
            ObservationMatchLog.created_at >= cutoff,
            ObservationMatchLog.requires_review.is_(True),
        )
        .order_by(ObservationMatchLog.created_at.desc())
        .limit(recent_observation_limit)
    ).scalars().all()
    logged = sum(match_status_counts.values())
    matched = sum(
        count
        for status, count in match_status_counts.items()
        if status.startswith("matched_")
    )
    unmatched = logged - matched
    requires_review = int(
        db.scalar(
            select(func.count(ObservationMatchLog.id)).where(
                ObservationMatchLog.provider == provider,
                ObservationMatchLog.created_at >= cutoff,
                ObservationMatchLog.requires_review.is_(True),
            )
        )
        or 0
    )
    return {
        "window": "24h",
        "observations_logged": logged,
        "observations_matched": matched,
        "observations_unmatched": unmatched,
        "observations_require_review": requires_review,
        "match_status_counts": match_status_counts,
        "recent_review_items": [
            {
                "provider": item.provider,
                "external_item_id": item.external_item_id,
                "raw_title": item.raw_title,
                "match_status": item.match_status,
                "confidence": _format_decimal(item.confidence),
                "reason": item.reason,
                "created_at": _to_iso(item.created_at),
            }
            for item in review_logs
        ],
    }


def _serialize_ingestion_result(ingestion_result: IngestionResult | None) -> dict[str, Any] | None:
    if ingestion_result is None:
        return None

    return {
        "cards_requested": ingestion_result.cards_requested,
        "cards_processed": ingestion_result.cards_processed,
        "cards_failed": ingestion_result.cards_failed,
        "cards_skipped_no_price": ingestion_result.cards_skipped_no_price,
        "assets_created": ingestion_result.assets_created,
        "assets_updated": ingestion_result.assets_updated,
        "price_points_inserted": ingestion_result.price_points_inserted,
        "price_points_changed": ingestion_result.price_points_changed,
        "price_points_unchanged": ingestion_result.price_points_unchanged,
        "price_points_skipped_existing_timestamp": ingestion_result.price_points_skipped_existing_timestamp,
        "sample_rows_deleted": ingestion_result.sample_rows_deleted,
        "observations_logged": ingestion_result.observations_logged,
        "observations_matched": ingestion_result.observations_matched,
        "observations_unmatched": ingestion_result.observations_unmatched,
        "observations_require_review": ingestion_result.observations_require_review,
        "observation_match_status_counts": dict(ingestion_result.observation_match_status_counts),
        "latest_captured_at": _to_iso(ingestion_result.latest_captured_at),
        "inserted_assets": list(ingestion_result.inserted_asset_names),
    }


def _build_signal_health_block(db: Session) -> dict:
    from backend.app.models.asset_signal import AssetSignal
    from backend.app.core.kpi_thresholds import kpi_status

    rows = db.execute(
        select(AssetSignal.label, func.count(AssetSignal.id)).group_by(AssetSignal.label)
    ).all()
    label_counts = {label: int(count) for label, count in rows}
    total = sum(label_counts.values())

    high_conf = int(
        db.scalar(
            select(func.count(AssetSignal.id)).where(AssetSignal.confidence >= 70)
        ) or 0
    )
    high_conf_pct = round(high_conf / total * 100, 1) if total else 0.0

    return {
        "status": "ok",
        "total_signals": total,
        "label_counts": label_counts,
        "high_confidence_count": high_conf,
        "high_confidence_pct": high_conf_pct,
        "kpi_status": kpi_status("high_conf_signal_pct", high_conf_pct),
    }


def _build_retry_queue_block(db: Session) -> dict:
    from backend.app.services.backfill_retry_service import get_queue_summary
    from backend.app.core.kpi_thresholds import kpi_status

    summary = get_queue_summary(db)
    pending = summary["total_pending"]
    permanent = summary["total_permanent"]

    pending_status = kpi_status("retry_queue_pending", pending)
    permanent_status = kpi_status("retry_queue_permanent", permanent)
    _rank = {"green": 0, "yellow": 1, "red": 2, "unknown": 0}
    overall = pending_status if _rank[pending_status] >= _rank[permanent_status] else permanent_status

    return {
        "status": overall,
        "total_pending": pending,
        "total_permanent": permanent,
        "by_failure_type": summary["by_failure_type"],
        "pending_kpi": pending_status,
        "permanent_kpi": permanent_status,
    }


def _build_scheduler_block(db: Session) -> dict:
    from backend.app.services.scheduler_run_log_service import (
        JOB_BACKFILL,
        JOB_INGESTION,
        JOB_RETRY,
        JOB_SIGNALS,
        get_last_run,
        serialize_run,
    )
    return {
        "ingestion": serialize_run(get_last_run(db, JOB_INGESTION)),
        "backfill":  serialize_run(get_last_run(db, JOB_BACKFILL)),
        "retry":     serialize_run(get_last_run(db, JOB_RETRY)),
        "signals":   serialize_run(get_last_run(db, JOB_SIGNALS)),
    }


def _build_missing_price_block(db: Session) -> dict:
    from sqlalchemy import exists, func
    from backend.app.core.kpi_thresholds import kpi_status
    from backend.app.models.asset import Asset
    from backend.app.models.price_history import PriceHistory

    total = int(db.scalar(select(func.count(Asset.id))) or 0) or 1
    missing = int(
        db.scalar(
            select(func.count(Asset.id)).where(
                ~exists(
                    select(PriceHistory.id)
                    .where(PriceHistory.asset_id == Asset.id)
                    .where(PriceHistory.source == POKEMON_TCG_PRICE_SOURCE)
                    .correlate(Asset)
                )
            )
        )
        or 0
    )
    pct = missing / total * 100
    return {
        "assets_missing_price": missing,
        "missing_price_pct": round(pct, 2),
        "missing_price_pct_status": kpi_status("missing_price_pct", pct),
    }


def _build_review_queue_block(db: Session) -> dict:
    from backend.app.core.kpi_thresholds import kpi_status

    pending = int(
        db.scalar(
            select(func.count(ObservationMatchLog.id)).where(
                ObservationMatchLog.requires_review.is_(True)
            )
        ) or 0
    )
    return {
        "status": "ok",
        "pending_count": pending,
        "kpi_status": kpi_status("review_backlog", pending),
    }


def build_standardized_diagnostics_summary(
    db: Session,
    *,
    ingestion_result: IngestionResult | None = None,  # deprecated: ignored, kept for caller compatibility
    recent_observation_limit: int = 5,
    scope_key: str | None = None,
    scope_label: str | None = None,
) -> dict[str, Any]:
    # ingestion_result is no longer used — the "ingestion" block is now populated from
    # scheduler_run_log via serialize_run(). The parameter is retained to avoid breaking
    # the 5 scripts that still pass it. Remove after those scripts are updated.
    _ = ingestion_result
    report = get_data_health_report(db, low_coverage_limit=recent_observation_limit)
    providers = get_configured_price_providers()
    primary_source = get_primary_price_source()
    primary_provider = next(
        (provider for provider in providers if provider.is_primary),
        providers[0] if providers else None,
    )

    observation_stage = _build_recent_observation_stage(
        db,
        provider=primary_source,
        recent_observation_limit=recent_observation_limit,
    )

    watchlist_count = int(db.scalar(select(func.count(Watchlist.id))) or 0)
    active_alert_count = int(
        db.scalar(select(func.count(Alert.id)).where(Alert.is_active.is_(True))) or 0
    )

    return {
        "generated_at": _to_iso(datetime.now(UTC)),
        "active_price_source": primary_source,
        "scope": {
            "key": scope_key,
            "label": scope_label,
        },
        "provider": {
            "source": primary_provider.source if primary_provider is not None else primary_source,
            "label": primary_provider.label if primary_provider is not None else "Unconfigured",
            "configured_provider_count": len(providers),
        },
        "smart_pool": _build_smart_pool_reference(report.pool_reports),
        "ingestion": _safe_block(_build_scheduler_block, db, block_name="ingestion"),
        "observation_stage": observation_stage,
        "health": {
            "total_assets": report.total_assets,
            "assets_with_real_history": report.assets_with_real_history,
            "assets_without_real_history": report.assets_without_real_history,
            "average_real_history_points_per_asset": _format_decimal(
                report.average_real_history_points_per_asset
            ),
            "recent_real_price_rows_last_24h": report.recent_real_price_rows_last_24h,
            "recent_real_price_rows_last_7d": report.recent_real_price_rows_last_7d,
            "assets_with_price_change_last_24h": report.assets_with_price_change_last_24h,
            "assets_with_price_change_last_7d": report.assets_with_price_change_last_7d,
            "row_change_pct_last_24h": _format_decimal(
                report.percent_recent_rows_changed_last_24h,
                suffix="%",
            ),
            "row_change_pct_last_7d": _format_decimal(
                report.percent_recent_rows_changed_last_7d,
                suffix="%",
            ),
            "assets_with_no_price_movement_full_history": report.assets_with_no_price_movement_full_history,
            "assets_with_unchanged_latest_price": report.assets_with_unchanged_latest_price,
        },
        "signal_layer": {
            "watchlists": watchlist_count,
            "active_alerts": active_alert_count,
        },
        "signal_health": _safe_block(_build_signal_health_block, db, block_name="signal_health"),
        "review_queue":  _safe_block(_build_review_queue_block, db, block_name="review_queue"),
        "backfill_retry_queue": _safe_block(_build_retry_queue_block,   db, block_name="backfill_retry_queue"),
        "scheduler":            _safe_block(_build_scheduler_block,     db, block_name="scheduler"),
        "missing_price":        _safe_block(_build_missing_price_block, db, block_name="missing_price"),
        "pools": [_serialize_pool(pool) for pool in report.pool_reports],
    }
