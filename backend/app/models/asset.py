from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.app.db.base import Base
from backend.app.models.enums import AssetClass


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint(
            "asset_class",
            "category",
            "name",
            "set_name",
            "card_number",
            "year",
            "language",
            "variant",
            "grade_company",
            "grade_score",
            name="uq_asset_identity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_class: Mapped[str] = mapped_column(String(32), nullable=False, default=AssetClass.TCG.value)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    set_name: Mapped[str | None] = mapped_column(String(255))
    card_number: Mapped[str | None] = mapped_column(String(64))
    year: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(String(32))
    variant: Mapped[str | None] = mapped_column(String(128))
    grade_company: Mapped[str | None] = mapped_column(String(32))
    grade_score: Mapped[float | None] = mapped_column(Numeric(4, 1))
    external_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSONB)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    price_history: Mapped[list["PriceHistory"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )
    watchlists: Mapped[list["Watchlist"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["Alert"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )
