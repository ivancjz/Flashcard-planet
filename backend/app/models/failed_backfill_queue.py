from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.app.db.base import Base


class FailedBackfillQueue(Base):
    __tablename__ = "failed_backfill_queue"
    __table_args__ = (
        Index("ix_fbq_asset_id", "asset_id"),
        Index("ix_fbq_permanent_attempted", "is_permanent", "last_attempted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    failure_type: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    last_attempted_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    is_permanent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    asset: Mapped["Asset"] = relationship("Asset")
