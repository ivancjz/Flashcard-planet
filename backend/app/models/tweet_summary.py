from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class TweetSummary(Base):
    __tablename__ = "tweet_summaries"
    __table_args__ = (
        UniqueConstraint("tweet_id", name="uq_tweet_summaries_tweet_id"),
        Index("ix_tweet_summaries_tweet_date", "tweet_date"),
        Index("ix_tweet_summaries_keyword", "keyword"),
    )

    id:          Mapped[int]               = mapped_column(Integer, primary_key=True, autoincrement=True)
    tweet_id:    Mapped[str]               = mapped_column(Text, nullable=False)
    keyword:     Mapped[str]               = mapped_column(Text, nullable=False)
    tweet_date:  Mapped[datetime]          = mapped_column(DateTime(timezone=True), nullable=False)
    summary:     Mapped[str]               = mapped_column(Text, nullable=False)
    embedding:   Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    captured_at: Mapped[datetime]          = mapped_column(DateTime(timezone=True), nullable=False)
