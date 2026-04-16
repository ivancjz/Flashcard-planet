from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class SchedulerRunLog(Base):
    __tablename__ = "scheduler_run_log"
    __table_args__ = (
        Index("ix_srl_job_name_started_at", "job_name", "started_at"),
    )

    id:              Mapped[int]            = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_name:        Mapped[str]            = mapped_column(String(64), nullable=False)
    started_at:      Mapped[datetime]       = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at:     Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status:          Mapped[str]            = mapped_column(String(16), nullable=False, default="running")
    records_written: Mapped[int]            = mapped_column(Integer, nullable=False, default=0)
    errors:          Mapped[int]            = mapped_column(Integer, nullable=False, default=0)
    error_message:   Mapped[str | None]     = mapped_column(Text, nullable=True)
    meta_json:       Mapped[dict | None]    = mapped_column(JSONB, nullable=True)
