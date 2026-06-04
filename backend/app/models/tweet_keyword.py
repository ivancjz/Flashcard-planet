from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class TweetKeyword(Base):
    __tablename__ = "tweet_keywords"

    id:                Mapped[int]           = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword:           Mapped[str]           = mapped_column(Text, nullable=False)
    game:              Mapped[str | None]    = mapped_column(Text, nullable=True)
    active:            Mapped[bool]          = mapped_column(Boolean, nullable=False, default=True)
    mention_count:     Mapped[int]           = mapped_column(Integer, nullable=False, default=0)
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:        Mapped[datetime]      = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
