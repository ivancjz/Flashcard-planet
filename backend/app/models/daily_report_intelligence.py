from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from backend.app.db.base import Base


class DailyReportIntelligence(Base):
    __tablename__ = "daily_report_intelligence"
    __table_args__ = (
        UniqueConstraint(
            "report_id",
            "evidence_hash",
            "prompt_version",
            name="uq_daily_report_intelligence_cache_key",
        ),
        CheckConstraint(
            "status IN ('pending', 'published', 'insufficient_evidence', 'failed')",
            name="ck_daily_report_intelligence_status",
        ),
        CheckConstraint(
            "attempt_count BETWEEN 0 AND 3",
            name="ck_daily_report_intelligence_attempt_count",
        ),
        Index(
            "ix_daily_report_intelligence_status_updated",
            "status",
            "updated_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("daily_market_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    commentary: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_observations_json: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )
    evidence_refs_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
