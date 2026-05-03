from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class DigestSendLog(Base):
    __tablename__ = "digest_send_log"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    sent_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )
    subject: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    cards_included: Mapped[Optional[list[str]]] = mapped_column(ARRAY(sa.Text), nullable=True)
    trigger_type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    delivery_status: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    dedupe_key: Mapped[str] = mapped_column(sa.String(64), unique=True, nullable=False)
