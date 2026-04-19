"""Signal detection service.

Classifies every asset with recent price history into one of four labels:

  BREAKOUT — High-confidence move ≥10% with strong liquidity. Act now.
  MOVE     — Moderate-confidence move ≥5%. Worth watching closely.
  WATCH    — Directional prediction (Up/Down) with enough history to trust.
  IDLE     — No meaningful signal detected.

Entry point: sweep_signals(db) — upserts one row per asset into asset_signals.
Called by the scheduler every SIGNAL_SWEEP_INTERVAL_SECONDS (default 900).
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.app.core.price_sources import get_active_price_source_filter
from backend.app.models.asset_signal_history import AssetSignalHistory
from backend.app.models.asset_signal import AssetSignal
from backend.app.models.enums import SignalLabel
from backend.app.models.price_history import PriceHistory
from backend.app.services.liquidity_service import get_asset_signal_snapshots
from backend.app.services.price_service import compute_prediction_from_recent_points

logger = logging.getLogger(__name__)

# ── Classification thresholds ─────────────────────────────────────────────────

BREAKOUT_CONFIDENCE_MIN = 70
BREAKOUT_DELTA_MIN = Decimal("10.0")
BREAKOUT_LIQUIDITY_MIN = 60

MOVE_CONFIDENCE_MIN = 40
MOVE_DELTA_MIN = Decimal("5.0")

WATCH_MIN_HISTORY = 3

# ── Sweep config ──────────────────────────────────────────────────────────────

ACTIVE_WINDOW_DAYS = 30
SWEEP_BATCH_SIZE = 500
PREDICTION_POINTS = 8


# ── Public result types ───────────────────────────────────────────────────────

@dataclass
class SignalRow:
    asset_id: Any
    label: SignalLabel
    confidence: int | None
    price_delta_pct: Decimal | None
    liquidity_score: int | None
    prediction: str | None
    computed_at: datetime


@dataclass
class SweepResult:
    total: int = 0
    breakout: int = 0
    move: int = 0
    watch: int = 0
    idle: int = 0
    errors: int = 0
    duration_ms: float = 0.0


# ── Classifier ────────────────────────────────────────────────────────────────

def classify_signal(
    *,
    alert_confidence: int | None,
    price_delta_pct: Decimal | None,
    liquidity_score: int,
    prediction: str | None,
    history_depth: int,
) -> SignalLabel:
    """Pure function — no I/O. Maps signal metrics to a label."""
    abs_delta = abs(price_delta_pct) if price_delta_pct is not None else None

    if (
        alert_confidence is not None
        and alert_confidence >= BREAKOUT_CONFIDENCE_MIN
        and abs_delta is not None
        and abs_delta >= BREAKOUT_DELTA_MIN
        and liquidity_score >= BREAKOUT_LIQUIDITY_MIN
    ):
        return SignalLabel.BREAKOUT

    if (
        alert_confidence is not None
        and alert_confidence >= MOVE_CONFIDENCE_MIN
        and abs_delta is not None
        and abs_delta >= MOVE_DELTA_MIN
    ):
        return SignalLabel.MOVE

    if prediction in ("Up", "Down") and history_depth >= WATCH_MIN_HISTORY:
        return SignalLabel.WATCH

    return SignalLabel.IDLE


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_active_asset_ids(db: Session, *, limit: int | None = None) -> list[Any]:
    """All asset_ids with at least one real price point in the last 30 days.

    When limit is set, returns the top-N by price-point count (most active first).
    """
    source_filter = get_active_price_source_filter(db)
    cutoff = datetime.now(UTC) - timedelta(days=ACTIVE_WINDOW_DAYS)
    stmt = (
        select(PriceHistory.asset_id, func.count().label("pts"))
        .where(source_filter, PriceHistory.captured_at >= cutoff)
        .group_by(PriceHistory.asset_id)
        .order_by(func.count().desc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = db.execute(stmt).all()
    return [row.asset_id for row in rows]


def _get_latest_two_prices(
    db: Session, asset_ids: list[Any]
) -> dict[Any, list[Decimal]]:
    """Returns the two most recent prices per asset (newest first)."""
    source_filter = get_active_price_source_filter(db)
    ranked = (
        select(
            PriceHistory.asset_id,
            PriceHistory.price,
            func.row_number()
            .over(
                partition_by=PriceHistory.asset_id,
                order_by=PriceHistory.captured_at.desc(),
            )
            .label("rn"),
        )
        .where(PriceHistory.asset_id.in_(asset_ids), source_filter)
        .subquery()
    )
    rows = db.execute(
        select(ranked.c.asset_id, ranked.c.price)
        .where(ranked.c.rn <= 2)
        .order_by(ranked.c.asset_id, ranked.c.rn)
    ).all()

    result: dict[Any, list[Decimal]] = {}
    for row in rows:
        result.setdefault(row.asset_id, []).append(Decimal(row.price))
    return result


def _get_recent_prices_for_prediction(
    db: Session, asset_ids: list[Any]
) -> dict[Any, list[tuple[Decimal, datetime]]]:
    """Returns up to PREDICTION_POINTS most recent (price, captured_at) pairs per
    asset, newest-first — matching the signature of compute_prediction_from_recent_points."""
    source_filter = get_active_price_source_filter(db)
    ranked = (
        select(
            PriceHistory.asset_id,
            PriceHistory.price,
            PriceHistory.captured_at,
            func.row_number()
            .over(
                partition_by=PriceHistory.asset_id,
                order_by=PriceHistory.captured_at.desc(),
            )
            .label("rn"),
        )
        .where(PriceHistory.asset_id.in_(asset_ids), source_filter)
        .subquery()
    )
    rows = db.execute(
        select(ranked.c.asset_id, ranked.c.price, ranked.c.captured_at)
        .where(ranked.c.rn <= PREDICTION_POINTS)
        .order_by(ranked.c.asset_id, ranked.c.rn)  # rn=1 is newest
    ).all()

    result: dict[Any, list[tuple[Decimal, datetime]]] = {}
    for row in rows:
        result.setdefault(row.asset_id, []).append(
            (Decimal(row.price), row.captured_at)
        )
    return result


def _upsert_signal(db: Session, *, signal: SignalRow) -> None:
    stmt = pg_insert(AssetSignal).values(
        id=uuid.uuid4(),
        asset_id=signal.asset_id,
        label=signal.label.value,
        confidence=signal.confidence,
        price_delta_pct=signal.price_delta_pct,
        liquidity_score=signal.liquidity_score,
        prediction=signal.prediction,
        computed_at=signal.computed_at,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["asset_id"],
        set_={
            "label": stmt.excluded.label,
            "confidence": stmt.excluded.confidence,
            "price_delta_pct": stmt.excluded.price_delta_pct,
            "liquidity_score": stmt.excluded.liquidity_score,
            "prediction": stmt.excluded.prediction,
            "computed_at": stmt.excluded.computed_at,
        },
    )
    db.execute(stmt)


def _append_history(db: Session, *, signal: SignalRow) -> None:
    db.add(
        AssetSignalHistory(
            asset_id=signal.asset_id,
            label=signal.label.value,
            confidence=signal.confidence,
            price_delta_pct=signal.price_delta_pct,
            liquidity_score=signal.liquidity_score,
            prediction=signal.prediction,
            computed_at=signal.computed_at,
        )
    )


# ── Sweep ─────────────────────────────────────────────────────────────────────

def sweep_signals(
    db: Session,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> SweepResult:
    """Classify all active assets and upsert their signal labels.

    Safe to re-run at any time — all writes are upserts.

    Args:
        dry_run: If True, walk the full classification logic but roll back all
                 DB writes at the end.  Useful for validating output before the
                 first production run.
        limit:   Process only the top-N most price-active assets.  None = all.
    """
    result = SweepResult()
    t_start = time.monotonic()

    asset_ids = _get_active_asset_ids(db, limit=limit)
    result.total = len(asset_ids)
    if not asset_ids:
        result.duration_ms = (time.monotonic() - t_start) * 1000
        return result

    for batch_start in range(0, len(asset_ids), SWEEP_BATCH_SIZE):
        batch = asset_ids[batch_start : batch_start + SWEEP_BATCH_SIZE]
        try:
            _process_batch(db, batch, result, commit=not dry_run)
        except Exception as exc:
            logger.exception("signal_sweep_batch_failed batch_start=%s error=%s", batch_start, exc)
            result.errors += len(batch)

    if dry_run:
        db.rollback()
        logger.info("signal_sweep_dry_run_rollback total_classified=%s", result.total)

    result.duration_ms = (time.monotonic() - t_start) * 1000
    logger.info(
        "signal_sweep_complete dry_run=%s total=%s breakout=%s move=%s watch=%s idle=%s errors=%s duration_ms=%.1f",
        dry_run, result.total, result.breakout, result.move, result.watch, result.idle,
        result.errors, result.duration_ms,
    )
    return result


def _process_batch(db: Session, asset_ids: list[Any], result: SweepResult, *, commit: bool = True) -> None:
    now = datetime.now(UTC)

    # Latest two prices → percent change
    latest_two = _get_latest_two_prices(db, asset_ids)
    percent_changes: dict[Any, Decimal] = {}
    for asset_id, prices in latest_two.items():
        if len(prices) >= 2 and prices[1] != 0:
            pct = ((prices[0] - prices[1]) / prices[1]) * Decimal("100")
            percent_changes[asset_id] = pct.quantize(Decimal("0.01"))

    # Signal snapshots (liquidity + alert_confidence, batched)
    snapshots = get_asset_signal_snapshots(
        db, asset_ids, percent_changes_by_asset=percent_changes, now=now
    )

    # Recent price history for prediction (batched)
    price_history = _get_recent_prices_for_prediction(db, asset_ids)

    for asset_id in asset_ids:
        snapshot = snapshots.get(asset_id)
        if snapshot is None:
            continue

        points_desc = price_history.get(asset_id, [])
        prediction_state = compute_prediction_from_recent_points(points_desc)
        prediction = (
            prediction_state.prediction
            if prediction_state.prediction != "Not enough data"
            else None
        )

        label = classify_signal(
            alert_confidence=snapshot.alert_confidence,
            price_delta_pct=percent_changes.get(asset_id),
            liquidity_score=snapshot.liquidity_score,
            prediction=prediction,
            history_depth=snapshot.history_depth,
        )

        _upsert_signal(
            db,
            signal=SignalRow(
                asset_id=asset_id,
                label=label,
                confidence=snapshot.alert_confidence,
                price_delta_pct=percent_changes.get(asset_id),
                liquidity_score=snapshot.liquidity_score,
                prediction=prediction,
                computed_at=now,
            ),
        )
        _append_history(
            db,
            signal=SignalRow(
                asset_id=asset_id,
                label=label,
                confidence=snapshot.alert_confidence,
                price_delta_pct=percent_changes.get(asset_id),
                liquidity_score=snapshot.liquidity_score,
                prediction=prediction,
                computed_at=now,
            ),
        )

        if label == SignalLabel.BREAKOUT:
            result.breakout += 1
        elif label == SignalLabel.MOVE:
            result.move += 1
        elif label == SignalLabel.WATCH:
            result.watch += 1
        else:
            result.idle += 1

    if commit:
        db.commit()


# ── Read helpers ──────────────────────────────────────────────────────────────

def get_signals_by_label(
    db: Session, label: SignalLabel, *, limit: int = 50
) -> list[AssetSignal]:
    return db.scalars(
        select(AssetSignal)
        .where(AssetSignal.label == label.value)
        .order_by(AssetSignal.computed_at.desc())
        .limit(limit)
    ).all()


def get_signal_for_asset(db: Session, asset_id: Any) -> AssetSignal | None:
    return db.scalars(
        select(AssetSignal).where(AssetSignal.asset_id == asset_id)
    ).first()


def get_all_signals(db: Session, *, limit: int = 200) -> list[AssetSignal]:
    return db.scalars(
        select(AssetSignal)
        .order_by(AssetSignal.label.asc(), AssetSignal.computed_at.desc())
        .limit(limit)
    ).all()


def get_daily_snapshot_signals(
    db: Session,
    *,
    label: str | None = None,
) -> list[AssetSignalHistory]:
    from datetime import timezone

    today_midnight = datetime.combine(
        date.today(), datetime.min.time(), tzinfo=timezone.utc
    )

    q = (
        select(AssetSignalHistory)
        .where(AssetSignalHistory.computed_at < today_midnight)
        .order_by(AssetSignalHistory.asset_id, AssetSignalHistory.computed_at.desc())
        .distinct(AssetSignalHistory.asset_id)
    )
    if label is not None:
        q = q.where(AssetSignalHistory.label == label)

    return list(db.scalars(q).all())
