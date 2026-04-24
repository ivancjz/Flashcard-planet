from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class AssetSignalHistory(Base):
    __tablename__ = "asset_signal_history"
    __table_args__ = (
        Index("ix_asset_signal_history_asset_computed", "asset_id", "computed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer)
    price_delta_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    liquidity_score: Mapped[int | None] = mapped_column(Integer)
    prediction: Mapped[str | None] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(nullable=False)
    signal_context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
