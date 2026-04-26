from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.app.db.base import Base


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="manual_seed")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False, index=True)
    market_segment: Mapped[str | None] = mapped_column(Text, nullable=True)
    grade_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    grade_score: Mapped[str | None] = mapped_column(Text, nullable=True)

    asset: Mapped["Asset"] = relationship(back_populates="price_history")
