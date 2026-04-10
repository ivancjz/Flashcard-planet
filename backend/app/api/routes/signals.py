from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.models.enums import SignalLabel
from backend.app.services.signal_explainer import get_or_explain
from backend.app.services.signal_service import (
    get_all_signals,
    get_signal_for_asset,
    get_signals_by_label,
)

router = APIRouter(prefix="/signals", tags=["signals"])


class SignalResponse(BaseModel):
    asset_id: uuid.UUID
    label: str
    confidence: int | None
    price_delta_pct: Decimal | None
    liquidity_score: int | None
    prediction: str | None
    computed_at: datetime
    explanation: str | None = None
    explained_at: datetime | None = None

    model_config = {"from_attributes": True}


class ExplainResponse(BaseModel):
    asset_id: uuid.UUID
    label: str
    explanation: str | None
    explained_at: datetime | None


@router.get("", response_model=list[SignalResponse])
def list_signals(
    label: str | None = Query(None, description="Filter by label: BREAKOUT, MOVE, WATCH, IDLE"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_database),
) -> list[SignalResponse]:
    if label is not None:
        try:
            signal_label = SignalLabel(label.upper())
        except ValueError:
            valid = ", ".join(sl.value for sl in SignalLabel)
            raise HTTPException(status_code=422, detail=f"Invalid label. Valid values: {valid}")
        rows = get_signals_by_label(db, signal_label, limit=limit)
    else:
        rows = get_all_signals(db, limit=limit)
    return [SignalResponse.model_validate(row) for row in rows]


@router.get("/{asset_id}", response_model=SignalResponse)
def get_signal(
    asset_id: uuid.UUID,
    db: Session = Depends(get_database),
) -> SignalResponse:
    row = get_signal_for_asset(db, asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No signal found for this asset.")
    return SignalResponse.model_validate(row)


@router.post("/{asset_id}/explain", response_model=ExplainResponse)
def explain_signal_endpoint(
    asset_id: uuid.UUID,
    refresh: bool = Query(False, description="Force regenerate even if cached"),
    db: Session = Depends(get_database),
) -> ExplainResponse:
    """Return an AI-generated explanation for why this asset received its signal.

    Results are cached on the signal row for up to EXPLANATION_MAX_AGE_HOURS (default 12h).
    Pass ?refresh=true to force regeneration.
    """
    row = get_signal_for_asset(db, asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="No signal found for this asset.")

    from backend.app.services.signal_explainer import explain_signal
    explanation = explain_signal(db, row) if refresh else get_or_explain(db, row)

    return ExplainResponse(
        asset_id=row.asset_id,
        label=row.label,
        explanation=explanation,
        explained_at=row.explained_at,
    )
