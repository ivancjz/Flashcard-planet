from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    discord_user_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(128))
    discriminator: Mapped[str | None] = mapped_column(String(16))
    global_name: Mapped[str | None] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    access_tier: Mapped[str] = mapped_column(String(16), nullable=False, server_default="free", default="free")
    tier_changed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    watchlists: Mapped[list["Watchlist"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["Alert"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.access_tier is None:
            self.access_tier = "free"
