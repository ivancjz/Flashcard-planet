from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(String(254), unique=True, nullable=True, index=True)
    google_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, index=True)
    discord_user_id: Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True, index=True)
    username: Mapped[str | None] = mapped_column(String(128))
    discriminator: Mapped[str | None] = mapped_column(String(16))
    global_name: Mapped[str | None] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    access_tier: Mapped[str] = mapped_column(String(16), nullable=False, server_default="free", default="free")
    tier_changed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Subscription fields (populated by LemonSqueezy webhook handler)
    # subscription_tier values: free | plus | pro
    # subscription_status values: free | trialing | active | past_due | cancelled | expired
    subscription_tier: Mapped[str] = mapped_column(String(16), nullable=False, server_default="free", default="free")
    subscription_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="free", default="free")
    subscription_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)           # 'lemonsqueezy'
    subscription_provider_id: Mapped[str | None] = mapped_column(String(128), nullable=True)       # LS subscription ID
    subscription_current_period_end: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    subscription_cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false", default=False)
    trial_started_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    is_founders: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false", default=False)
    founders_locked_price_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    # Market Digest preferences
    digest_frequency: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="daily", default="daily"
    )
    last_digest_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_users_subscription_status", "subscription_status"),
    )

    watchlists: Mapped[list["Watchlist"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["Alert"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.access_tier is None:
            self.access_tier = "free"
        if self.digest_frequency is None:
            self.digest_frequency = "daily"
