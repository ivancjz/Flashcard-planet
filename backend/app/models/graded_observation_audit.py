"""Temporary audit table for Phase 0 graded shadow admission.

Holds graded eBay listings that passed asset compatibility gates but were
withheld from price_history. Used for human review of parser precision
before Phase 3 graded enablement is designed. Drop when Phase 3 decision
is made.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class GradedObservationAudit(Base):
    __tablename__ = "graded_observation_audit"
    __table_args__ = (
        UniqueConstraint(
            "provider", "external_item_id", "candidate_asset_id",
            name="uq_graded_audit_provider_item_asset",
        ),
        Index("ix_graded_audit_decision_reviewed_created",
              "shadow_decision", "human_reviewed_at", "created_at"),
        Index("ix_graded_audit_segment_created",
              "parser_market_segment", "created_at"),
        Index("ix_graded_audit_asset_created",
              "candidate_asset_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    external_item_id: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False
    )
    raw_title: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="USD")
    captured_at: Mapped[datetime | None] = mapped_column(nullable=True)
    parser_market_segment: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser_grade_company: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser_grade_score: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser_confidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    parser_notes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    preflight_grade_info: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    shadow_decision: Mapped[str] = mapped_column(Text, nullable=False)
    human_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    reviewer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=datetime.utcnow
    )
