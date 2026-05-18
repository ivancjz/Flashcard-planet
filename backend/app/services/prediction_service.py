"""prediction_service.py — Public Calls Phase 1.

Manages the lifecycle of predictions:
  create_prediction  — insert a locked prediction + audit row
  resolve_prediction — mark HIT/MISS + audit row
  get_calibration_metrics — Brier score + reliability bins for public page

Immutability of predicted_at, resolution_date, threshold_value, stated_probability
is enforced at the DB trigger level (migration 0035). This service also validates
inputs before INSERT to surface errors early.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.models.predictions import Prediction, PredictionAudit

_VALID_DIRECTIONS = frozenset({"above", "below", "within_band"})
_VALID_DRIVERS = frozenset({
    "MACRO", "META_SHIFT", "SUPPLY_SHOCK",
    "EVENT_DRIVEN", "INFLUENCER_PROVENANCE", "UNKNOWN",
})


# ── return types ───────────────────────────────────────────────────────────

@dataclass
class PredictionResolution:
    prediction_id: uuid.UUID
    resolution_status: str
    actual_value: Decimal
    resolved_at: datetime


@dataclass
class ReliabilityBin:
    prob_bin_low: float
    prob_bin_high: float
    n: int
    hit_rate: float
    ci_low: float
    ci_high: float


@dataclass
class CalibrationMetrics:
    total_calls: int
    total_resolved: int
    brier_score: float | None
    brier_baseline: float = 0.25
    reliability_bins: list[ReliabilityBin] = field(default_factory=list)
    methodology_version: str = ""


# ── pure math helpers ──────────────────────────────────────────────────────

def _brier_score(predictions: list[tuple[float, int]]) -> float | None:
    """Mean Brier score. Input: list of (stated_probability, outcome).
    outcome is 1 for HIT, 0 for MISS. Returns None on empty input.
    """
    if not predictions:
        return None
    return sum((p - o) ** 2 for p, o in predictions) / len(predictions)


def _wilson_ci(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% confidence interval for a proportion. Returns (lower, upper)."""
    if n == 0:
        return 0.0, 1.0
    p = hits / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = (z / denom) * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)
    return max(0.0, centre - margin), min(1.0, centre + margin)


def _build_reliability_bins(resolved: list[tuple[float, int]]) -> list[ReliabilityBin]:
    """Bin predictions into 10 decile buckets; compute hit_rate + Wilson CI."""
    bins = []
    for i in range(10):
        low, high = i / 10, (i + 1) / 10
        bucket = [
            (p, o) for p, o in resolved
            if low <= p < high or (i == 9 and p == 1.0)
        ]
        n = len(bucket)
        hits = sum(o for _, o in bucket)
        ci_low, ci_high = _wilson_ci(hits, n)
        bins.append(ReliabilityBin(
            prob_bin_low=low, prob_bin_high=high, n=n,
            hit_rate=hits / n if n > 0 else 0.0,
            ci_low=ci_low, ci_high=ci_high,
        ))
    return bins


def _evaluate_threshold(
    *,
    actual_value: Decimal,
    threshold_value: Decimal,
    threshold_direction: str,
    threshold_band_high: Decimal | None,
) -> str:
    if threshold_direction == "above":
        return "HIT" if actual_value >= threshold_value else "MISS"
    if threshold_direction == "below":
        return "HIT" if actual_value <= threshold_value else "MISS"
    if threshold_direction == "within_band" and threshold_band_high is not None:
        return "HIT" if threshold_value <= actual_value <= threshold_band_high else "MISS"
    return "MISS"


# ── service functions ──────────────────────────────────────────────────────

def create_prediction(
    db: Session,
    *,
    asset_id: uuid.UUID,
    prediction_text: str,
    threshold_value: Decimal,
    threshold_direction: str,
    stated_probability: Decimal,
    resolution_date: datetime,
    methodology_version: str,
    threshold_currency: str = "USD",
    threshold_band_high: Decimal | None = None,
    driver_attribution: str | None = None,
    driver_confidence: Decimal | None = None,
    is_paper: bool = True,
    notes: str | None = None,
    predicted_at: datetime | None = None,
) -> uuid.UUID:
    """Insert a new prediction + audit row. Returns the prediction UUID."""
    if threshold_direction not in _VALID_DIRECTIONS:
        raise ValueError(
            f"threshold_direction must be one of {sorted(_VALID_DIRECTIONS)}, "
            f"got {threshold_direction!r}"
        )
    if not (Decimal("0") <= stated_probability <= Decimal("1")):
        raise ValueError(
            f"stated_probability must be between 0 and 1, got {stated_probability}"
        )
    if threshold_direction == "within_band" and threshold_band_high is None:
        raise ValueError(
            "threshold_band_high is required when threshold_direction='within_band'"
        )
    if driver_attribution is not None and driver_attribution not in _VALID_DRIVERS:
        raise ValueError(
            f"driver_attribution must be one of {sorted(_VALID_DRIVERS)}, "
            f"got {driver_attribution!r}"
        )

    now = predicted_at or datetime.now(UTC)
    prediction_id = uuid.uuid4()

    prediction = Prediction(
        id=prediction_id,
        predicted_at=now,
        resolution_date=resolution_date,
        asset_id=asset_id,
        prediction_text=prediction_text,
        threshold_value=threshold_value,
        threshold_currency=threshold_currency,
        threshold_direction=threshold_direction,
        threshold_band_high=threshold_band_high,
        stated_probability=stated_probability,
        driver_attribution=driver_attribution,
        driver_confidence=driver_confidence,
        methodology_version=methodology_version,
        is_paper=is_paper,
        resolution_status="PENDING",
        notes=notes,
    )
    db.add(prediction)

    audit = PredictionAudit(
        prediction_id=prediction_id,
        action="INSERT",
        changed_at=now,
        old_state=None,
        new_state={
            "resolution_status": "PENDING",
            "is_paper": is_paper,
            "stated_probability": str(stated_probability),
        },
    )
    db.add(audit)
    db.commit()
    return prediction_id


def resolve_prediction(
    db: Session,
    *,
    prediction_id: uuid.UUID,
    actual_value: Decimal,
    resolved_at: datetime | None = None,
) -> PredictionResolution:
    """Mark a PENDING prediction HIT or MISS. Writes audit row."""
    row: Prediction | None = db.scalars(
        select(Prediction).where(Prediction.id == prediction_id)
    ).first()

    if row is None:
        raise ValueError(f"Prediction {prediction_id} not found")
    if row.resolution_status != "PENDING":
        raise ValueError(
            f"Prediction {prediction_id} already resolved: {row.resolution_status}"
        )

    now = resolved_at or datetime.now(UTC)
    status = _evaluate_threshold(
        actual_value=actual_value,
        threshold_value=Decimal(str(row.threshold_value)),
        threshold_direction=row.threshold_direction,
        threshold_band_high=(
            Decimal(str(row.threshold_band_high))
            if row.threshold_band_high is not None else None
        ),
    )

    row.resolution_status = status
    row.resolved_at = now
    row.actual_value = actual_value

    db.add(PredictionAudit(
        prediction_id=prediction_id,
        action="RESOLVE",
        changed_at=now,
        old_state={"resolution_status": "PENDING"},
        new_state={"resolution_status": status, "actual_value": str(actual_value)},
    ))
    db.commit()

    return PredictionResolution(
        prediction_id=prediction_id,
        resolution_status=status,
        actual_value=actual_value,
        resolved_at=now,
    )


def get_calibration_metrics(
    db: Session,
    *,
    only_public: bool = True,
    methodology_version: str = "",
) -> CalibrationMetrics:
    """Compute Brier score + reliability bins from all resolved predictions."""
    resolved_q = select(Prediction).where(
        Prediction.resolution_status.in_(["HIT", "MISS"])
    )
    if only_public:
        resolved_q = resolved_q.where(Prediction.is_paper.is_(False))
    resolved = db.scalars(resolved_q).all()

    count_q = select(func.count()).select_from(Prediction)
    if only_public:
        count_q = count_q.where(Prediction.is_paper.is_(False))
    total_calls = db.scalar(count_q) or 0

    pairs = [
        (float(r.stated_probability), 1 if r.resolution_status == "HIT" else 0)
        for r in resolved
    ]
    return CalibrationMetrics(
        total_calls=total_calls,
        total_resolved=len(resolved),
        brier_score=_brier_score(pairs),
        reliability_bins=_build_reliability_bins(pairs),
        methodology_version=methodology_version,
    )
