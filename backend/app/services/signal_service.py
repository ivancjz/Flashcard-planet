"""Signal detection service.

Classifies every asset with recent price history into one of five labels:

  BREAKOUT          — High-confidence move ≥10% with strong liquidity. Act now.
  MOVE              — Moderate-confidence move ≥5%. Worth watching closely.
  WATCH             — Directional prediction (Up/Down) with enough history to trust.
  IDLE              — No meaningful signal detected.
  INSUFFICIENT_DATA — Not enough price history to compute a reliable delta.

Entry point: sweep_signals(db) — upserts one row per asset into asset_signals.
Called by the scheduler every SIGNAL_SWEEP_INTERVAL_SECONDS (default 900).
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.app.core.config import settings
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

# Cards historically priced below this floor are bulk noise — large deltas from a
# single eBay sale against a $0.09 baseline produce 12000%+ BREAKOUT signals that
# have no investment meaning.
SIGNAL_BULK_FLOOR_PRICE = Decimal("0.50")

# Minimum number of price points in the current 24-hour window to compute a
# signal. Single-sale spikes ($0.70 baseline → $350 one-off) produce thousands-
# of-percent false BREAKOUT/MOVE labels. Three points is the smallest sample
# that lets IQR filtering have any effect.
MIN_CURRENT_N_FOR_SIGNAL = 3

# ── Sweep config ──────────────────────────────────────────────────────────────

ACTIVE_WINDOW_DAYS = 30
SWEEP_BATCH_SIZE = 100
PREDICTION_POINTS = 8


# ── Source weight parsing ─────────────────────────────────────────────────────

def _parse_source_weights(raw: str) -> dict[str, float]:
    """Parse 'ebay_sold=2.0,pokemon_tcg_api=1.0' into {source: weight}."""
    weights: dict[str, float] = {}
    for part in raw.split(","):
        part = part.strip()
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        try:
            weights[k.strip()] = float(v.strip())
        except ValueError:
            pass
    return weights


# ── Weighted median ───────────────────────────────────────────────────────────

def _weighted_median(prices_with_weights: list[tuple[Decimal, float]]) -> Decimal:
    """Pure function — no I/O. Returns the weighted median of (price, weight) pairs."""
    if not prices_with_weights:
        raise ValueError("empty input")
    sorted_pairs = sorted(prices_with_weights, key=lambda x: x[0])
    total_weight = sum(w for _, w in sorted_pairs)
    cumulative = Decimal("0")
    half = Decimal(str(total_weight / 2))
    for price, weight in sorted_pairs:
        cumulative += Decimal(str(weight))
        if cumulative >= half:
            return price
    return sorted_pairs[-1][0]


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
    signal_context: dict | None = field(default=None)


@dataclass
class SweepResult:
    total: int = 0
    breakout: int = 0
    move: int = 0
    watch: int = 0
    idle: int = 0
    insufficient_data: int = 0
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
    # Only positive delta triggers BREAKOUT/MOVE — a large price DROP has high
    # abs_delta but is not a buy signal. Using signed comparison fixes the bug
    # where 35/66 BREAKOUT cards had negative price_delta_pct.
    if (
        alert_confidence is not None
        and alert_confidence >= BREAKOUT_CONFIDENCE_MIN
        and price_delta_pct is not None
        and price_delta_pct >= BREAKOUT_DELTA_MIN
        and liquidity_score >= BREAKOUT_LIQUIDITY_MIN
    ):
        return SignalLabel.BREAKOUT

    if (
        alert_confidence is not None
        and alert_confidence >= MOVE_CONFIDENCE_MIN
        and price_delta_pct is not None
        and price_delta_pct >= MOVE_DELTA_MIN
    ):
        return SignalLabel.MOVE

    # WATCH requires non-negative delta — a falling card is never WATCH regardless
    # of its directional prediction. Negative delta → IDLE, full stop.
    if (
        prediction in ("Up", "Down")
        and history_depth >= WATCH_MIN_HISTORY
        and price_delta_pct is not None
        and price_delta_pct >= 0
    ):
        return SignalLabel.WATCH

    return SignalLabel.IDLE


# ── Downgrade rules ───────────────────────────────────────────────────────────

def _apply_signal_downgrade(
    candidate: SignalLabel,
    *,
    current_price: Decimal,
    baseline_price: Decimal,
    baseline_n: int,
) -> tuple[SignalLabel, str | None]:
    """Apply price-floor and baseline-sample-size downgrade rules.

    Downgrade is chained (BREAKOUT→MOVE→WATCH→IDLE), never a jump.
    Returns (final_label, downgrade_reason | None).
    """
    # Bulk gate: any signal from a card whose historical baseline is below $0.50 is
    # noise (e.g. $0.09 TCG → $12 single eBay sale). Applies to all candidates, not
    # just BREAKOUT/MOVE — a WATCH on a $0.04 card is equally meaningless.
    # Returns INSUFFICIENT_DATA so delta is nulled and card sinks to the bottom of
    # sort-by-change (NULLS LAST) rather than cluttering the top.
    if baseline_price < SIGNAL_BULK_FLOOR_PRICE:
        return SignalLabel.INSUFFICIENT_DATA, "bulk_baseline_price"

    breakout_min_price = Decimal(str(settings.signal_breakout_min_price_usd))
    move_min_price = Decimal(str(settings.signal_move_min_price_usd))
    breakout_min_n = settings.signal_breakout_min_baseline_n

    if candidate == SignalLabel.BREAKOUT:
        if current_price < breakout_min_price:
            candidate = SignalLabel.MOVE
            return candidate, "low_absolute_price"
        if baseline_n < breakout_min_n:
            candidate = SignalLabel.MOVE
            return candidate, "insufficient_baseline_n"

    if candidate == SignalLabel.MOVE:
        if current_price < move_min_price:
            return SignalLabel.WATCH, "low_absolute_price"

    return candidate, None


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_active_asset_ids(db: Session, *, limit: int | None = None) -> list[Any]:
    """All asset_ids with at least one real price point in the last 30 days.

    When limit is set, returns the top-N by price-point count (most active first).
    """
    cutoff = datetime.now(UTC) - timedelta(days=ACTIVE_WINDOW_DAYS)
    stmt = (
        select(PriceHistory.asset_id, func.count().label("pts"))
        .where(PriceHistory.captured_at >= cutoff)
        .group_by(PriceHistory.asset_id)
        .order_by(func.count().desc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = db.execute(stmt).all()
    return [row.asset_id for row in rows]


def _get_recent_prices_for_prediction(
    db: Session, asset_ids: list[Any]
) -> dict[Any, list[tuple[Decimal, datetime]]]:
    """Returns up to PREDICTION_POINTS most recent (price, captured_at) pairs per
    asset, newest-first — matching the signature of compute_prediction_from_recent_points."""
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
        .where(PriceHistory.asset_id.in_(asset_ids))
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


# ── Delta algorithm (multi-source, windowed) ──────────────────────────────────

def _parse_source_weights_from_settings() -> dict[str, float]:
    return _parse_source_weights(settings.signal_delta_source_weights)


def compute_signal_delta(
    db: Session,
    asset_id: Any,
    *,
    baseline_window_days: int | None = None,
    current_window_hours: int | None = None,
    source_weights: dict[str, float] | None = None,
    now: datetime | None = None,
) -> tuple[Decimal | None, dict]:
    """Compute percent-change delta for a single asset (for testing and ad-hoc use).

    Returns (delta_pct, context_dict).
    delta_pct is None when there is insufficient data.
    """
    if now is None:
        now = datetime.now(UTC)
    if baseline_window_days is None:
        baseline_window_days = settings.signal_baseline_window_days
    if current_window_hours is None:
        current_window_hours = settings.signal_current_window_hours
    if source_weights is None:
        source_weights = _parse_source_weights_from_settings()

    result = _compute_delta_batch(
        db,
        [asset_id],
        baseline_window_days=baseline_window_days,
        current_window_hours=current_window_hours,
        source_weights=source_weights,
        now=now,
    )
    return result.get(asset_id, (None, {"reason": "no_data"}))


_BASELINE_SAMPLE_POINTS = 5   # how many rows to sample around the baseline cutoff
_CURRENT_SAMPLE_POINTS = 10  # how many recent rows to use for the current price


def _compute_delta_batch(
    db: Session,
    asset_ids: list[Any],
    *,
    baseline_window_days: int,
    current_window_hours: int,
    source_weights: dict[str, float],
    now: datetime,
) -> dict[Any, tuple[Decimal | None, dict]]:
    """Compute windowed weighted-median delta for a batch of assets.

    Returns {asset_id: (delta_pct | None, context_dict)}.

    Baseline price = weighted median of the _BASELINE_SAMPLE_POINTS most
      recent rows per asset captured BEFORE (now - baseline_window_days).
      This is robust to data gaps — it finds the nearest available data to
      the baseline cutoff without requiring data in a specific 24h slice.

    Current price  = weighted median of the _CURRENT_SAMPLE_POINTS most
      recent rows per asset captured in the last current_window_hours.

    Unknown sources default to weight 1.0.
    """
    baseline_cutoff = now - timedelta(days=baseline_window_days)
    current_start = now - timedelta(hours=current_window_hours)

    # ── Baseline: most recent N rows per asset before the baseline cutoff ──
    baseline_ranked = (
        select(
            PriceHistory.asset_id,
            PriceHistory.price,
            PriceHistory.source,
            PriceHistory.captured_at,
            func.row_number()
            .over(
                partition_by=PriceHistory.asset_id,
                order_by=PriceHistory.captured_at.desc(),
            )
            .label("rn"),
        )
        .where(
            PriceHistory.asset_id.in_(asset_ids),
            PriceHistory.captured_at <= baseline_cutoff,
        )
        .subquery()
    )
    baseline_rows = db.execute(
        select(
            baseline_ranked.c.asset_id,
            baseline_ranked.c.price,
            baseline_ranked.c.source,
            baseline_ranked.c.captured_at,
        ).where(baseline_ranked.c.rn <= _BASELINE_SAMPLE_POINTS)
    ).all()

    # ── Current: most recent N rows per asset in the current window ────────
    current_ranked = (
        select(
            PriceHistory.asset_id,
            PriceHistory.price,
            PriceHistory.source,
            PriceHistory.captured_at,
            func.row_number()
            .over(
                partition_by=PriceHistory.asset_id,
                order_by=PriceHistory.captured_at.desc(),
            )
            .label("rn"),
        )
        .where(
            PriceHistory.asset_id.in_(asset_ids),
            PriceHistory.captured_at >= current_start,
            PriceHistory.captured_at <= now,
        )
        .subquery()
    )
    current_rows = db.execute(
        select(
            current_ranked.c.asset_id,
            current_ranked.c.price,
            current_ranked.c.source,
        ).where(current_ranked.c.rn <= _CURRENT_SAMPLE_POINTS)
    ).all()

    # Bucket into per-asset weighted price lists
    baseline_by_asset: dict[Any, list[tuple[Decimal, float]]] = {}
    for row in baseline_rows:
        w = source_weights.get(row.source, 1.0)
        baseline_by_asset.setdefault(row.asset_id, []).append((Decimal(str(row.price)), w))

    current_by_asset: dict[Any, list[tuple[Decimal, float]]] = {}
    for row in current_rows:
        w = source_weights.get(row.source, 1.0)
        current_by_asset.setdefault(row.asset_id, []).append((Decimal(str(row.price)), w))

    result: dict[Any, tuple[Decimal | None, dict]] = {}

    for asset_id in asset_ids:
        baseline_pairs = baseline_by_asset.get(asset_id, [])
        current_pairs = current_by_asset.get(asset_id, [])

        ctx: dict = {
            "baseline_n": len(baseline_pairs),
            "current_n": len(current_pairs),
            "baseline_window_days": baseline_window_days,
            "current_window_hours": current_window_hours,
        }

        if not baseline_pairs:
            ctx["reason"] = "no_baseline_data"
            result[asset_id] = (None, ctx)
            continue

        if not current_pairs:
            ctx["reason"] = "no_current_data"
            result[asset_id] = (None, ctx)
            continue

        baseline_price = _weighted_median(baseline_pairs)
        current_price = _weighted_median(current_pairs)

        ctx["baseline_price"] = float(baseline_price)
        ctx["current_price"] = float(current_price)

        if baseline_price == 0:
            ctx["reason"] = "zero_baseline"
            result[asset_id] = (None, ctx)
            continue

        delta = ((current_price - baseline_price) / baseline_price * Decimal("100")).quantize(Decimal("0.01"))
        ctx["delta_pct"] = float(delta)
        result[asset_id] = (delta, ctx)

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
        signal_context=signal.signal_context,
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
            "signal_context": stmt.excluded.signal_context,
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
            signal_context=signal.signal_context,
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

    source_weights = _parse_source_weights_from_settings()
    baseline_window_days = settings.signal_baseline_window_days
    current_window_hours = settings.signal_current_window_hours

    for batch_start in range(0, len(asset_ids), SWEEP_BATCH_SIZE):
        batch = asset_ids[batch_start : batch_start + SWEEP_BATCH_SIZE]
        try:
            _process_batch(
                db,
                batch,
                result,
                commit=not dry_run,
                source_weights=source_weights,
                baseline_window_days=baseline_window_days,
                current_window_hours=current_window_hours,
            )
        except Exception as exc:
            logger.exception("signal_sweep_batch_failed batch_start=%s error=%s", batch_start, exc)
            result.errors += len(batch)

    if dry_run:
        db.rollback()
        logger.info("signal_sweep_dry_run_rollback total_classified=%s", result.total)

    result.duration_ms = (time.monotonic() - t_start) * 1000
    logger.info(
        "signal_sweep_complete dry_run=%s total=%s breakout=%s move=%s watch=%s "
        "idle=%s insufficient_data=%s errors=%s duration_ms=%.1f",
        dry_run, result.total, result.breakout, result.move, result.watch, result.idle,
        result.insufficient_data, result.errors, result.duration_ms,
    )
    return result


def _process_batch(
    db: Session,
    asset_ids: list[Any],
    result: SweepResult,
    *,
    commit: bool = True,
    source_weights: dict[str, float],
    baseline_window_days: int,
    current_window_hours: int,
) -> None:
    now = datetime.now(UTC)

    # Compute windowed deltas for the whole batch
    delta_batch = _compute_delta_batch(
        db,
        asset_ids,
        baseline_window_days=baseline_window_days,
        current_window_hours=current_window_hours,
        source_weights=source_weights,
        now=now,
    )

    # Build percent_changes for assets that have a valid delta
    percent_changes: dict[Any, Decimal] = {}
    for asset_id, (delta, _ctx) in delta_batch.items():
        if delta is not None:
            percent_changes[asset_id] = delta

    # Signal snapshots (liquidity + alert_confidence, batched)
    snapshots = get_asset_signal_snapshots(
        db, asset_ids, percent_changes_by_asset=percent_changes, now=now
    )

    # Recent price history for prediction (batched)
    price_history = _get_recent_prices_for_prediction(db, asset_ids)

    for asset_id in asset_ids:
        delta, ctx = delta_batch.get(asset_id, (None, {"reason": "no_data"}))

        # Assets with no delta → INSUFFICIENT_DATA, skip classification
        if delta is None:
            signal = SignalRow(
                asset_id=asset_id,
                label=SignalLabel.INSUFFICIENT_DATA,
                confidence=None,
                price_delta_pct=None,
                liquidity_score=None,
                prediction=None,
                computed_at=now,
                signal_context=ctx,
            )
            _upsert_signal(db, signal=signal)
            _append_history(db, signal=signal)
            result.insufficient_data += 1
            continue

        # Hard floor: too few baseline samples → no reliable signal
        baseline_n = ctx.get("baseline_n", 0)
        if baseline_n < settings.signal_move_min_baseline_n:
            ctx["downgrade_reason"] = "insufficient_baseline_n"
            signal = SignalRow(
                asset_id=asset_id,
                label=SignalLabel.INSUFFICIENT_DATA,
                confidence=None,
                price_delta_pct=delta,
                liquidity_score=None,
                prediction=None,
                computed_at=now,
                signal_context=ctx,
            )
            _upsert_signal(db, signal=signal)
            _append_history(db, signal=signal)
            result.insufficient_data += 1
            continue

        # Hard floor: too few current samples → single-sale noise, not a signal.
        current_n = ctx.get("current_n", 0)
        if current_n < MIN_CURRENT_N_FOR_SIGNAL:
            ctx["downgrade_reason"] = "insufficient_current_n"
            signal = SignalRow(
                asset_id=asset_id,
                label=SignalLabel.INSUFFICIENT_DATA,
                confidence=None,
                price_delta_pct=delta,
                liquidity_score=None,
                prediction=None,
                computed_at=now,
                signal_context=ctx,
            )
            _upsert_signal(db, signal=signal)
            _append_history(db, signal=signal)
            result.insufficient_data += 1
            continue

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

        candidate = classify_signal(
            alert_confidence=snapshot.alert_confidence,
            price_delta_pct=delta,
            liquidity_score=snapshot.liquidity_score,
            prediction=prediction,
            history_depth=snapshot.history_depth,
        )

        current_price = Decimal(str(ctx.get("current_price", 0)))
        baseline_price = Decimal(str(ctx.get("baseline_price", 0)))
        label, downgrade_reason = _apply_signal_downgrade(
            candidate, current_price=current_price, baseline_price=baseline_price, baseline_n=baseline_n
        )
        if downgrade_reason:
            ctx["original_candidate_label"] = candidate.value
            ctx["downgrade_reason"] = downgrade_reason

        # Bulk-downgraded cards become INSUFFICIENT_DATA with null delta so they
        # sink to the bottom of sort-by-change (NULLS LAST) rather than polluting
        # the top with noise like +77678%.
        stored_delta = None if downgrade_reason == "bulk_baseline_price" else delta

        signal = SignalRow(
            asset_id=asset_id,
            label=label,
            confidence=snapshot.alert_confidence,
            price_delta_pct=stored_delta,
            liquidity_score=snapshot.liquidity_score,
            prediction=prediction,
            computed_at=now,
            signal_context=ctx,
        )
        _upsert_signal(db, signal=signal)
        _append_history(db, signal=signal)

        if label == SignalLabel.BREAKOUT:
            result.breakout += 1
        elif label == SignalLabel.MOVE:
            result.move += 1
        elif label == SignalLabel.WATCH:
            result.watch += 1
        elif label == SignalLabel.INSUFFICIENT_DATA:
            result.insufficient_data += 1
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
