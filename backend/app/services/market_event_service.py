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
from decimal import Decimal
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from backend.app.models.enums import CatalystEventType
from backend.app.models.predictions import MarketEvent


CATALYST_EVENT_TYPES = frozenset(event_type.value for event_type in CatalystEventType)
DEFAULT_CATALYST_WINDOW_DAYS = 14


def resolve_catalyst_window_days(expected_window_days: int | None) -> int:
    if expected_window_days is None:
        return DEFAULT_CATALYST_WINDOW_DAYS
    if expected_window_days < 0:
        raise ValueError("market_event expected_window_days cannot be negative")
    return expected_window_days


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
    affected_games: list[str]
    affected_asset_ids: Optional[list] = None
    affected_set_ids: Optional[list] = None
    expected_window_days: Optional[int] = None
    impact_score: Optional[int] = None
    confidence_score: Optional[Decimal] = None


def create_market_event(db: Session, data: MarketEventCreate) -> MarketEvent:
    """Insert a curated market event after validating its type, scope, and evidence.

    EvidenceMissingError is raised when source_url is unusable or verified_at
    is absent, consistent with the DB CHECK constraint added in migration 0037.
    """
    event_type = data.event_type.strip().upper()
    if event_type not in CATALYST_EVENT_TYPES:
        raise ValueError(f"unsupported market_event event_type: {data.event_type!r}")

    if not data.affected_games:
        raise ValueError("market_event affected_games must contain at least one game")
    affected_games = [game.strip().lower() for game in data.affected_games]
    if any(not game for game in affected_games):
        raise ValueError("market_event affected_games cannot contain empty values")

    if data.impact_score is not None and not 0 <= data.impact_score <= 100:
        raise ValueError("market_event impact_score must be between 0 and 100")
    if data.confidence_score is not None and not 0 <= data.confidence_score <= 100:
        raise ValueError("market_event confidence_score must be between 0 and 100")
    resolve_catalyst_window_days(data.expected_window_days)

    if not data.source_url or not data.source_url.strip():
        raise EvidenceMissingError(
            f"market_event '{data.description[:60]}' requires source_url "
            "(Evidence Discipline: naked claims without URLs are unverified)"
        )
    parsed_source_url = urlparse(data.source_url.strip())
    if parsed_source_url.scheme.lower() not in {"http", "https"} or not parsed_source_url.netloc:
        raise EvidenceMissingError(
            f"market_event '{data.description[:60]}' requires a valid http(s) source_url"
        )
    if data.verified_at is None:
        raise EvidenceMissingError(
            f"market_event '{data.description[:60]}' requires verified_at "
            "(Evidence Discipline: mark when the claim was verified)"
        )

    event = MarketEvent(
        id=uuid.uuid4(),
        event_date=data.event_date,
        event_type=event_type,
        description=data.description,
        source_url=data.source_url,
        verified_at=data.verified_at,
        verified_by=data.verified_by,
        affected_games=affected_games,
        affected_asset_ids=data.affected_asset_ids or [],
        affected_set_ids=data.affected_set_ids or [],
        expected_window_days=data.expected_window_days,
        impact_score=data.impact_score,
        confidence_score=data.confidence_score,
    )
    db.add(event)
    db.flush()
    return event
