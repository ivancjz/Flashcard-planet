"""
Service layer for market_events creation.

Evidence discipline: every MarketEvent must have source_url + verified_at
before it can be inserted. This mirrors the CLAUDE.md §3 Evidence Discipline
rule — naked claims without URLs are unverified by default.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.app.models.predictions import MarketEvent


class EvidenceMissingError(ValueError):
    """Raised when a market event lacks required evidence fields."""


@dataclass
class MarketEventCreate:
    event_date: datetime
    event_type: str
    description: str
    source_url: str
    verified_at: datetime
    verified_by: str
    affected_asset_ids: Optional[list] = None
    affected_set_ids: Optional[list] = None
    expected_window_days: Optional[int] = None


def create_market_event(db: Session, data: MarketEventCreate) -> MarketEvent:
    """Insert a market event after validating evidence fields.

    Raises EvidenceMissingError if source_url or verified_at are absent —
    consistent with the DB CHECK constraint added in migration 0037.
    """
    if not data.source_url or not data.source_url.strip():
        raise EvidenceMissingError(
            f"market_event '{data.description[:60]}' requires source_url "
            "(Evidence Discipline: naked claims without URLs are unverified)"
        )
    if data.verified_at is None:
        raise EvidenceMissingError(
            f"market_event '{data.description[:60]}' requires verified_at "
            "(Evidence Discipline: mark when the claim was verified)"
        )

    event = MarketEvent(
        id=uuid.uuid4(),
        event_date=data.event_date,
        event_type=data.event_type,
        description=data.description,
        source_url=data.source_url,
        verified_at=data.verified_at,
        verified_by=data.verified_by,
        affected_asset_ids=data.affected_asset_ids or [],
        affected_set_ids=data.affected_set_ids or [],
        expected_window_days=data.expected_window_days,
    )
    db.add(event)
    db.flush()
    return event
