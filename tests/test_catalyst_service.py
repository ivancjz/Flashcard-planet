from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.app.models.predictions import MarketEvent
from backend.app.services.catalyst_service import (
    catalyst_lifecycle,
    get_catalyst,
    list_catalysts,
    market_event_to_catalyst_response,
)


AS_OF = datetime(2026, 7, 22, 12, tzinfo=UTC)


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


def _uuid(value: int) -> UUID:
    return UUID(hex=f"a{value:031x}")


def _event(**overrides) -> MarketEvent:
    data = {
        "id": _uuid(1),
        "event_date": AS_OF - timedelta(days=1),
        "event_type": "RELEASE",
        "description": "Verified catalyst",
        "source_url": "https://example.com/catalyst",
        "affected_games": ["pokemon"],
        "affected_asset_ids": ["asset-1"],
        "affected_set_ids": ["set-1"],
        "expected_window_days": 14,
        "impact_score": 75,
        "confidence_score": Decimal("82.50"),
        "verified_at": AS_OF - timedelta(hours=2),
        "verified_by": "market-ops",
    }
    data.update(overrides)
    return MarketEvent(**data)


def _persist(session: Session, *events: MarketEvent) -> None:
    session.add_all(events)
    session.commit()
    session.expunge_all()


@pytest.mark.parametrize(
    ("event_date", "window_days", "as_of", "expected"),
    [
        (AS_OF + timedelta(microseconds=1), 7, AS_OF, "upcoming"),
        (AS_OF.replace(tzinfo=None), 7, AS_OF, "active"),
        (AS_OF - timedelta(days=3), 3, AS_OF, "active"),
        (
            AS_OF - timedelta(days=3, microseconds=1),
            3,
            AS_OF,
            "expired",
        ),
        (AS_OF - timedelta(days=14), None, AS_OF, "active"),
        (AS_OF - timedelta(days=5), 6, AS_OF.replace(tzinfo=None), "active"),
    ],
)
def test_catalyst_lifecycle_boundaries_and_windows(
    event_date, window_days, as_of, expected
):
    event = SimpleNamespace(
        event_date=event_date,
        expected_window_days=window_days,
    )

    assert catalyst_lifecycle(event, as_of=as_of) == expected


def test_zero_window_is_active_exactly_at_event_date():
    response = market_event_to_catalyst_response(
        _event(event_date=AS_OF, expected_window_days=0),
        as_of=AS_OF,
    )

    assert response.status == "active"
    assert response.active_until == AS_OF


def test_zero_window_expires_one_microsecond_after_event_date():
    event = SimpleNamespace(event_date=AS_OF, expected_window_days=0)

    assert catalyst_lifecycle(
        event,
        as_of=AS_OF + timedelta(microseconds=1),
    ) == "expired"


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (None, "unscored"),
        (0, "low"),
        (49, "low"),
        (50, "medium"),
        (79, "medium"),
        (80, "high"),
        (100, "high"),
    ],
)
def test_impact_label_boundaries(score, expected):
    response = market_event_to_catalyst_response(
        _event(impact_score=score),
        as_of=AS_OF,
    )

    assert response.impact_label == expected


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (None, "insufficient_data"),
        (Decimal("0"), "low"),
        (Decimal("49"), "low"),
        (Decimal("50"), "medium"),
        (Decimal("79"), "medium"),
        (Decimal("80"), "high"),
        (Decimal("100"), "high"),
    ],
)
def test_confidence_label_boundaries(score, expected):
    response = market_event_to_catalyst_response(
        _event(confidence_score=score),
        as_of=AS_OF,
    )

    assert response.confidence_label == expected


def test_mapper_exposes_default_and_explicit_active_until():
    default_window = market_event_to_catalyst_response(
        _event(event_date=AS_OF, expected_window_days=None),
        as_of=AS_OF,
    )
    explicit_window = market_event_to_catalyst_response(
        _event(event_date=AS_OF, expected_window_days=3),
        as_of=AS_OF,
    )

    assert default_window.active_until == AS_OF + timedelta(days=14)
    assert explicit_window.active_until == AS_OF + timedelta(days=3)
    assert default_window.active_until.tzinfo is UTC


def test_list_filters_selected_game_with_global_and_no_game_keeps_all(
    sqlite_market_event_session,
):
    global_event = _event(
        id=_uuid(10), affected_games=["global"], impact_score=90
    )
    pokemon_event = _event(
        id=_uuid(11), affected_games=["pokemon"], impact_score=80
    )
    yugioh_event = _event(
        id=_uuid(12), affected_games=["yugioh"], impact_score=70
    )
    unverified = _event(id=_uuid(13), verified_at=None, impact_score=100)
    blank_source = _event(id=_uuid(14), source_url="   ", impact_score=100)
    missing_source = _event(id=_uuid(15), source_url=None, impact_score=100)
    _persist(
        sqlite_market_event_session,
        global_event,
        pokemon_event,
        yugioh_event,
        unverified,
        blank_source,
        missing_source,
    )

    pokemon = list_catalysts(
        sqlite_market_event_session,
        game="PoKeMoN",
        as_of=AS_OF,
    )
    all_games = list_catalysts(sqlite_market_event_session, as_of=AS_OF)

    assert [item.id for item in pokemon.catalysts] == [_uuid(10), _uuid(11)]
    assert [item.id for item in all_games.catalysts] == [
        _uuid(10),
        _uuid(11),
        _uuid(12),
    ]
    assert all_games.total == 3


def test_list_excludes_tab_newline_only_source_and_preserves_valid_url(
    sqlite_market_event_session,
):
    valid_source_url = "https://example.com/valid-catalyst"
    valid = _event(id=_uuid(70), source_url=valid_source_url)
    fully_blank = _event(id=_uuid(71), source_url="\t\n", impact_score=100)
    _persist(sqlite_market_event_session, valid, fully_blank)

    result = list_catalysts(sqlite_market_event_session, as_of=AS_OF)

    assert [item.id for item in result.catalysts] == [_uuid(70)]
    assert result.catalysts[0].source_url == valid_source_url
    assert result.total == 1


def test_status_combinations_are_repeatable_and_keep_lifecycle_group_order(
    sqlite_market_event_session,
):
    active = _event(id=_uuid(20), event_date=AS_OF - timedelta(days=1))
    upcoming = _event(id=_uuid(21), event_date=AS_OF + timedelta(days=1))
    expired = _event(id=_uuid(22), event_date=AS_OF - timedelta(days=20))
    _persist(sqlite_market_event_session, active, upcoming, expired)

    first = list_catalysts(
        sqlite_market_event_session,
        statuses=["expired", "active"],
        as_of=AS_OF,
    )
    second = list_catalysts(
        sqlite_market_event_session,
        statuses=["active", "expired", "active"],
        as_of=AS_OF,
    )

    assert [item.id for item in first.catalysts] == [_uuid(20), _uuid(22)]
    assert [item.id for item in second.catalysts] == [_uuid(20), _uuid(22)]


def test_event_type_filter_is_case_normalized_and_exact(
    sqlite_market_event_session,
):
    release = _event(id=_uuid(30), event_type="RELEASE")
    reprint = _event(id=_uuid(31), event_type="REPRINT")
    _persist(sqlite_market_event_session, release, reprint)

    result = list_catalysts(
        sqlite_market_event_session,
        event_type="release",
        as_of=AS_OF,
    )

    assert [item.id for item in result.catalysts] == [_uuid(30)]


def test_list_uses_exact_three_group_order_and_null_impact_positions(
    sqlite_market_event_session,
):
    shared_active_date = AS_OF - timedelta(days=2)
    events = [
        _event(id=_uuid(2), event_date=shared_active_date, impact_score=80),
        _event(id=_uuid(1), event_date=shared_active_date, impact_score=80),
        _event(id=_uuid(3), event_date=AS_OF, impact_score=50),
        _event(id=_uuid(4), event_date=AS_OF, impact_score=None),
        _event(
            id=_uuid(5), event_date=AS_OF + timedelta(days=1), impact_score=None
        ),
        _event(
            id=_uuid(6), event_date=AS_OF + timedelta(days=1), impact_score=90
        ),
        _event(
            id=_uuid(7), event_date=AS_OF + timedelta(days=2), impact_score=100
        ),
        _event(
            id=_uuid(8), event_date=AS_OF - timedelta(days=20), impact_score=None
        ),
        _event(
            id=_uuid(9), event_date=AS_OF - timedelta(days=20), impact_score=90
        ),
        _event(
            id=_uuid(10), event_date=AS_OF - timedelta(days=30), impact_score=100
        ),
    ]
    _persist(sqlite_market_event_session, *events)

    result = list_catalysts(sqlite_market_event_session, as_of=AS_OF)

    assert [item.id for item in result.catalysts] == [
        _uuid(1),
        _uuid(2),
        _uuid(3),
        _uuid(4),
        _uuid(6),
        _uuid(5),
        _uuid(7),
        _uuid(9),
        _uuid(8),
        _uuid(10),
    ]
    assert [item.status for item in result.catalysts] == [
        "active",
        "active",
        "active",
        "active",
        "upcoming",
        "upcoming",
        "upcoming",
        "expired",
        "expired",
        "expired",
    ]


def test_list_total_limit_offset_and_utc_as_of(sqlite_market_event_session):
    events = [
        _event(id=_uuid(40 + index), impact_score=100 - index)
        for index in range(5)
    ]
    _persist(sqlite_market_event_session, *events)

    full = list_catalysts(sqlite_market_event_session, as_of=AS_OF)
    page = list_catalysts(
        sqlite_market_event_session,
        limit=2,
        offset=1,
        as_of=AS_OF.replace(tzinfo=None),
    )

    assert page.total == 5
    assert page.limit == 2
    assert page.offset == 1
    assert page.as_of == AS_OF
    assert page.as_of.tzinfo is UTC
    assert [item.id for item in page.catalysts] == [
        item.id for item in full.catalysts[1:3]
    ]


def test_get_catalyst_detail_and_public_contract(sqlite_market_event_session):
    event = _event(
        id=_uuid(50),
        event_date=AS_OF.replace(tzinfo=None),
        expected_window_days=5,
        affected_asset_ids=None,
        affected_set_ids=None,
    )
    _persist(sqlite_market_event_session, event)

    result = get_catalyst(sqlite_market_event_session, _uuid(50), as_of=AS_OF)

    assert result is not None
    assert result.id == _uuid(50)
    assert result.event_date == AS_OF
    assert result.active_until == AS_OF + timedelta(days=5)
    assert result.affected_asset_ids == []
    assert result.affected_set_ids == []
    assert result.status == "active"
    assert result.verified_at == AS_OF - timedelta(hours=2)
    assert "verified_by" not in result.model_dump()


def test_get_catalyst_returns_none_for_missing_unverified_or_blank_source(
    sqlite_market_event_session,
):
    unverified = _event(id=_uuid(60), verified_at=None)
    blank_source = _event(id=_uuid(61), source_url=" ")
    _persist(sqlite_market_event_session, unverified, blank_source)

    assert (
        get_catalyst(sqlite_market_event_session, _uuid(999), as_of=AS_OF) is None
    )
    assert get_catalyst(sqlite_market_event_session, _uuid(60), as_of=AS_OF) is None
    assert get_catalyst(sqlite_market_event_session, _uuid(61), as_of=AS_OF) is None


def test_get_catalyst_returns_none_for_tab_newline_only_source(
    sqlite_market_event_session,
):
    fully_blank = _event(id=_uuid(72), source_url="\t\n")
    _persist(sqlite_market_event_session, fully_blank)

    assert get_catalyst(sqlite_market_event_session, _uuid(72), as_of=AS_OF) is None
