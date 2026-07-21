from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import backend.app.services.market_event_service as market_event_service
from backend.app.models.daily_market_report import DailyMarketReport
from backend.app.models.predictions import MarketEvent
from backend.app.services.market_event_service import MarketEventCreate, create_market_event


EXPECTED_CATALYST_EVENT_TYPES = frozenset(
    {
        "INFLUENCER",
        "SUPPLY",
        "TOURNAMENT",
        "RELEASE",
        "REPRINT",
        "PRICE_CHANGE",
        "ANNIVERSARY",
        "COLLABORATION",
        "LIMITED_PRODUCT",
        "POLICY",
        "SOCIAL_TREND",
    }
)


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest.fixture
def sqlite_market_event_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    MarketEvent.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _valid_event(**overrides) -> MarketEventCreate:
    data = MarketEventCreate(
        event_date=datetime(2026, 7, 24, tzinfo=UTC),
        event_type="REPRINT",
        description="Verified regional reprint announcement.",
        source_url="https://www.pokemon.com/example",
        verified_at=datetime(2026, 7, 22, tzinfo=UTC),
        verified_by="market-ops",
        affected_games=["pokemon"],
        affected_asset_ids=[],
        affected_set_ids=["sv08"],
        expected_window_days=21,
        impact_score=78,
        confidence_score=Decimal("91.50"),
    )
    return replace(data, **overrides)


def test_catalyst_event_types_are_exact_and_immutable():
    assert market_event_service.CATALYST_EVENT_TYPES == EXPECTED_CATALYST_EVENT_TYPES
    assert isinstance(market_event_service.CATALYST_EVENT_TYPES, frozenset)


def test_create_market_event_persists_every_field(sqlite_market_event_session):
    data = _valid_event()

    event = create_market_event(sqlite_market_event_session, data)
    event_id = event.id
    sqlite_market_event_session.commit()
    sqlite_market_event_session.expunge_all()

    stored = sqlite_market_event_session.scalar(
        select(MarketEvent).where(MarketEvent.id == event_id)
    )

    assert stored is not None
    assert stored.id == event_id
    assert stored.event_date == data.event_date.replace(tzinfo=None)
    assert stored.event_type == data.event_type
    assert stored.description == data.description
    assert stored.source_url == data.source_url
    assert stored.verified_at == data.verified_at.replace(tzinfo=None)
    assert stored.verified_by == data.verified_by
    assert stored.affected_games == data.affected_games
    assert stored.affected_asset_ids == data.affected_asset_ids
    assert stored.affected_set_ids == data.affected_set_ids
    assert stored.expected_window_days == data.expected_window_days
    assert stored.impact_score == data.impact_score
    assert stored.confidence_score == Decimal("91.50")
    assert stored.created_at is not None


def test_create_market_event_normalizes_type_and_games():
    event = create_market_event(
        MagicMock(),
        _valid_event(event_type="reprint", affected_games=["Pokemon", "YUGIOH"]),
    )

    assert event.event_type == "REPRINT"
    assert event.affected_games == ["pokemon", "yugioh"]


def test_create_market_event_preserves_unscored_values_as_none():
    event = create_market_event(
        MagicMock(),
        _valid_event(impact_score=None, confidence_score=None),
    )

    assert event.impact_score is None
    assert event.confidence_score is None


def test_create_market_event_rejects_unknown_event_type():
    with pytest.raises(ValueError, match="event_type"):
        create_market_event(MagicMock(), _valid_event(event_type="RUMOR"))


def test_create_market_event_rejects_empty_affected_games():
    with pytest.raises(ValueError, match="affected_games"):
        create_market_event(MagicMock(), _valid_event(affected_games=[]))


@pytest.mark.parametrize("impact_score", [-1, 101])
def test_create_market_event_rejects_impact_score_outside_range(impact_score):
    with pytest.raises(ValueError, match="impact_score"):
        create_market_event(
            MagicMock(),
            _valid_event(impact_score=impact_score),
        )


@pytest.mark.parametrize("confidence_score", [Decimal("-0.01"), Decimal("100.01")])
def test_create_market_event_rejects_confidence_score_outside_range(confidence_score):
    with pytest.raises(ValueError, match="confidence_score"):
        create_market_event(
            MagicMock(),
            _valid_event(confidence_score=confidence_score),
        )


@pytest.mark.parametrize(
    "source_url",
    [
        "ftp://www.pokemon.com/example",
        "https:///example",
        "www.pokemon.com/example",
    ],
)
def test_create_market_event_rejects_invalid_source_url(source_url):
    with pytest.raises(ValueError, match="source_url"):
        create_market_event(MagicMock(), _valid_event(source_url=source_url))


def test_create_market_event_rejects_missing_verified_at():
    with pytest.raises(ValueError, match="verified_at"):
        create_market_event(MagicMock(), _valid_event(verified_at=None))


def test_json_list_columns_use_callable_defaults():
    affected_games = MarketEvent.__table__.c.affected_games
    catalysts_json = DailyMarketReport.__table__.c.catalysts_json

    assert affected_games.nullable is False
    assert callable(affected_games.default.arg)
    first_affected_games = affected_games.default.arg(None)
    assert first_affected_games == []
    assert first_affected_games is not affected_games.default.arg(None)
    assert catalysts_json.nullable is False
    assert callable(catalysts_json.default.arg)
    first_catalysts = catalysts_json.default.arg(None)
    assert first_catalysts == []
    assert first_catalysts is not catalysts_json.default.arg(None)
