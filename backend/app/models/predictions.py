from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from backend.app.db.base import Base


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolution_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    prediction_text: Mapped[str] = mapped_column(Text, nullable=False)
    threshold_value: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    threshold_currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    threshold_direction: Mapped[str] = mapped_column(String(16), nullable=False)
    threshold_band_high: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    stated_probability: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    driver_attribution: Mapped[str | None] = mapped_column(String(32), nullable=True)
    driver_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    methodology_version: Mapped[str] = mapped_column(String(64), nullable=False)
    is_paper: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    resolution_status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PredictionAudit(Base):
    __tablename__ = "predictions_audit"

    audit_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    prediction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    changed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    old_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class MarketEvent(Base):
    __tablename__ = "market_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_games: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    affected_asset_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    affected_set_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    expected_window_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    impact_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
