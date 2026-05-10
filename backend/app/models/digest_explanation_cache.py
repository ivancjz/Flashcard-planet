from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class DigestExplanationCache(Base):
    __tablename__ = "digest_explanation_cache"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("assets.id"), nullable=False
    )
    signal_type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    date_utc: Mapped[date] = mapped_column(sa.Date, nullable=False)
    explanation: Mapped[str] = mapped_column(sa.Text, nullable=False)
    generated_by: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )
