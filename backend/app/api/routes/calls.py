"""calls.py — Public Calls API endpoints (Phase 2).

GET /api/v1/calls/list?status=all|pending|resolved
GET /api/v1/calls/calibration
GET /api/v1/calls/{prediction_id}

All endpoints return only is_paper=FALSE predictions.
"""
from __future__ import annotations

import subprocess
import uuid as _uuid
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.models.predictions import Prediction
from backend.app.services.prediction_service import (
    get_calibration_metrics,
    list_predictions,
)

router = APIRouter(prefix="/calls", tags=["calls"])


@lru_cache(maxsize=1)
def _methodology_version() -> str:
    """Derive 'v0.1-{7-char git hash}'. Cached for process lifetime."""
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short=7", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=2,
        ).decode().strip()
        return f"v0.1-{sha}"
    except Exception:
        return "v0.1-unknown"


def _serialize_prediction(p: Prediction) -> dict:
    return {
        "id": str(p.id),
        "predicted_at": p.predicted_at.isoformat() if p.predicted_at else None,
        "resolution_date": p.resolution_date.isoformat() if p.resolution_date else None,
        "asset_id": str(p.asset_id),
        "prediction_text": p.prediction_text,
        "threshold_value": str(p.threshold_value) if p.threshold_value is not None else None,
        "threshold_currency": p.threshold_currency,
        "threshold_direction": p.threshold_direction,
        "threshold_band_high": str(p.threshold_band_high) if p.threshold_band_high is not None else None,
        "stated_probability": float(p.stated_probability) if p.stated_probability is not None else None,
        "driver_attribution": p.driver_attribution,
        "driver_confidence": float(p.driver_confidence) if p.driver_confidence is not None else None,
        "methodology_version": p.methodology_version,
        "resolution_status": p.resolution_status,
        "resolved_at": p.resolved_at.isoformat() if p.resolved_at else None,
        "actual_value": str(p.actual_value) if p.actual_value is not None else None,
        "notes": p.notes,
    }


@router.get("/list")
def get_calls_list(
    status: str = Query(default="all", pattern="^(all|pending|resolved)$"),
    db: Session = Depends(get_database),
) -> dict:
    """List public predictions. Resolved sorted first."""
    predictions = list_predictions(db, status=status, only_public=True)
    return {
        "status_filter": status,
        "count": len(predictions),
        "predictions": [_serialize_prediction(p) for p in predictions],
    }


@router.get("/calibration")
def get_calibration(db: Session = Depends(get_database)) -> dict:
    """Brier score, reliability bins, and aggregate metrics."""
    metrics = get_calibration_metrics(
        db,
        only_public=True,
        methodology_version=_methodology_version(),
    )
    return {
        "total_calls": metrics.total_calls,
        "total_resolved": metrics.total_resolved,
        "brier_score": metrics.brier_score,
        "brier_baseline": metrics.brier_baseline,
        "reliability_bins": [
            {
                "prob_bin_low": b.prob_bin_low,
                "prob_bin_high": b.prob_bin_high,
                "n": b.n,
                "hit_rate": b.hit_rate,
                "ci_low": b.ci_low,
                "ci_high": b.ci_high,
            }
            for b in metrics.reliability_bins
        ],
        "methodology_version": metrics.methodology_version,
    }


@router.get("/{prediction_id}")
def get_call_detail(
    prediction_id: str,
    db: Session = Depends(get_database),
) -> dict:
    """Single prediction detail. Only public (is_paper=FALSE) predictions."""
    try:
        uid = _uuid.UUID(prediction_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid prediction_id format")

    p: Prediction | None = db.scalars(
        select(Prediction).where(
            Prediction.id == uid,
            Prediction.is_paper.is_(False),
        )
    ).first()
    if p is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return _serialize_prediction(p)
