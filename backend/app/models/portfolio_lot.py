from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.app.db.base import Base


class PortfolioLot(Base):
    __tablename__ = "portfolio_lots"
    __table_args__ = (
        CheckConstraint(
            "quantity > 0",
            name="ck_portfolio_lots_quantity_positive",
        ),
        CheckConstraint(
            "unit_cost_usd >= 0",
            name="ck_portfolio_lots_unit_cost_non_negative",
        ),
        Index(
            "ix_portfolio_lots_user_asset",
            "user_id",
            "asset_id",
        ),
        Index(
            "ix_portfolio_lots_user_purchased_on",
            "user_id",
            text("purchased_on DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assets.id"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    purchased_on: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="portfolio_lots")
    asset: Mapped["Asset"] = relationship(back_populates="portfolio_lots")
