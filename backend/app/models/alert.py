from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.app.db.base import Base
from backend.app.models.enums import AlertDirection, AlertType


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True
    )
    watchlist_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("watchlists.id"))
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False, default=AlertType.TARGET_PRICE_HIT.value)
    direction: Mapped[str | None] = mapped_column(String(16), default=AlertDirection.ABOVE.value)
    threshold_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_armed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_observed_signal: Mapped[str | None] = mapped_column(String(32))
    last_triggered_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship(back_populates="alerts")
    asset: Mapped["Asset"] = relationship(back_populates="alerts")
    watchlist: Mapped[Watchlist | None] = relationship(back_populates="alerts")
    history: Mapped[list["AlertHistory"]] = relationship(
        back_populates="alert", cascade="all, delete-orphan", passive_deletes=True
    )
