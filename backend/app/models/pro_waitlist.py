from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from backend.app.db.base import Base


class ProWaitlist(Base):
    __tablename__ = "pro_waitlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    signed_up_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now(), nullable=False)
    source_page: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locale: Mapped[str | None] = mapped_column(String(16), nullable=True)
    ip_country: Mapped[str | None] = mapped_column(String(4), nullable=True)
