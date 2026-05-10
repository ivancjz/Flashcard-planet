from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.app.db.base import Base


class ObservationMatchLog(Base):
    __tablename__ = "observation_match_logs"
    __table_args__ = (
        Index(
            "ix_observation_match_logs_provider_item_created",
            "provider",
            "external_item_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    external_item_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    raw_title: Mapped[str | None] = mapped_column(String(255))
    raw_set_name: Mapped[str | None] = mapped_column(String(255))
    raw_card_number: Mapped[str | None] = mapped_column(String(64))
    raw_language: Mapped[str | None] = mapped_column(String(32))
    matched_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id"),
        index=True,
    )
    canonical_key: Mapped[str | None] = mapped_column(String(512), index=True)
    match_status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, default=Decimal("0.00"))
    reason: Mapped[str | None] = mapped_column(Text)
    requires_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False, index=True)
    market_segment: Mapped[str | None] = mapped_column(Text, nullable=True)
    grade_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    grade_score: Mapped[str | None] = mapped_column(Text, nullable=True)

    matched_asset = relationship("Asset")
