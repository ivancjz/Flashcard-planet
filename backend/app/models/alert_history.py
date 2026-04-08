from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.app.db.base import Base


class AlertHistory(Base):
    """Immutable record of each alert trigger event.

    Denormalises key fields (alert_type, asset_name, etc.) so the history
    remains readable even after the parent alert or asset is modified or deleted.
    Foreign keys are nullable to preserve history on cascade deletes.
    """

    __tablename__ = "alert_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Soft-FK: nullable so history survives alert deletion.
    alert_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Denormalised columns — snapshot at trigger time so history stays self-contained.
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_name: Mapped[str] = mapped_column(String(255), nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(nullable=False, index=True)
    price_at_trigger: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    reference_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    percent_change: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    notification_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_status: Mapped[str] = mapped_column(String(16), nullable=False, default="sent")

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    alert: Mapped["Alert | None"] = relationship(back_populates="history")
    user: Mapped["User"] = relationship()
    asset: Mapped["Asset"] = relationship()
