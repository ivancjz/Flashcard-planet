from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from backend.app.db.base import Base


class AssetSignal(Base):
    """Stores the most recent computed signal label for each asset.

    One row per asset — sweep_signals() upserts on asset_id.
    """

    __tablename__ = "asset_signals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, unique=True, index=True
    )
    label: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    confidence: Mapped[int | None] = mapped_column(Integer)
    price_delta_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    liquidity_score: Mapped[int | None] = mapped_column(Integer)
    prediction: Mapped[str | None] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    explained_at: Mapped[datetime | None] = mapped_column()
