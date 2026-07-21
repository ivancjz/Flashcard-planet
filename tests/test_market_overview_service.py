from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
from backend.app.db.base import Base
from backend.app.models.asset import Asset
from backend.app.models.asset_signal import AssetSignal
from backend.app.models.price_history import PriceHistory
from backend.app.services.market_overview_service import get_market_overview


def _coerce_postgres_types_for_sqlite() -> None:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


@pytest.fixture
def sqlite_db():
    _coerce_postgres_types_for_sqlite()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with session_local() as db:
        yield db
    Base.metadata.drop_all(engine)
    engine.dispose()


def _asset(db, *, name: str, game: str = "pokemon") -> Asset:
    row = Asset(
        name=name,
        game=game,
        category=game.title(),
        external_id=f"{game}-{name.lower().replace(' ', '-')}",
    )
    db.add(row)
    db.flush()
    return row


def _price(
    db,
    asset: Asset,
    *,
    price: str,
    captured_at: datetime,
    market_segment: str = "raw",
    source: str = "sample_seed",
) -> None:
    db.add(
        PriceHistory(
            asset_id=asset.id,
            price=Decimal(price),
            currency="USD",
            source=source,
            captured_at=captured_at,
            market_segment=market_segment,
        )
    )


def test_market_overview_groups_raw_indexes_and_ignores_graded_observations(sqlite_db):
    earlier = datetime(2026, 7, 20, 10, 0, 0)
    latest = datetime(2026, 7, 21, 10, 0, 0)

    charizard = _asset(sqlite_db, name="Charizard", game="pokemon")
    moonbreon = _asset(sqlite_db, name="Moonbreon", game="pokemon")
    blue_eyes = _asset(sqlite_db, name="Blue-Eyes White Dragon", game="yugioh")
    graded_shadow = _asset(sqlite_db, name="Graded Shadow", game="pokemon")

    _price(sqlite_db, charizard, price="100.00", captured_at=earlier)
    _price(sqlite_db, charizard, price="120.00", captured_at=latest)
    _price(sqlite_db, moonbreon, price="50.00", captured_at=earlier)
    _price(sqlite_db, moonbreon, price="55.00", captured_at=latest)
    _price(sqlite_db, blue_eyes, price="10.00", captured_at=earlier)
    _price(sqlite_db, blue_eyes, price="8.00", captured_at=latest)
    _price(sqlite_db, graded_shadow, price="100.00", captured_at=earlier, market_segment="graded")
    _price(sqlite_db, graded_shadow, price="5000.00", captured_at=latest, market_segment="graded")

    sqlite_db.add(
        AssetSignal(
            asset_id=charizard.id,
            label="BREAKOUT",
            confidence=88,
            price_delta_pct=Decimal("20.00"),
            liquidity_score=80,
            prediction="Up",
            computed_at=latest,
        )
    )
    sqlite_db.add(
        AssetSignal(
            asset_id=moonbreon.id,
            label="MOVE",
            confidence=72,
            price_delta_pct=Decimal("10.00"),
            liquidity_score=65,
            prediction="Up",
            computed_at=latest,
        )
    )
    sqlite_db.commit()

    overview = get_market_overview(sqlite_db, mover_limit=5)

    assert overview.market_sentiment == "bullish"
    assert overview.confidence_label == "medium"
    assert [index.game for index in overview.indexes] == ["pokemon", "yugioh"]

    pokemon_index = overview.indexes[0]
    assert pokemon_index.label == "Pokemon Market"
    assert pokemon_index.change_pct == Decimal("15.00")
    assert pokemon_index.direction == "up"
    assert pokemon_index.observed_assets == 2
    assert pokemon_index.current_assets == 2

    mover_names = {mover.name for mover in overview.top_movers}
    assert "Charizard" in mover_names
    assert "Blue-Eyes White Dragon" in mover_names
    assert "Graded Shadow" not in mover_names

    signal_counts = {row.label: row.count for row in overview.signal_summary}
    assert signal_counts == {"BREAKOUT": 1, "MOVE": 1}
    assert "raw price series" in overview.commentary
    assert any("market_segment=raw" in item for item in overview.evidence)


def test_market_overview_returns_insufficient_data_without_comparable_raw_series(sqlite_db):
    pikachu = _asset(sqlite_db, name="Pikachu", game="pokemon")
    _price(
        sqlite_db,
        pikachu,
        price="12.00",
        captured_at=datetime(2026, 7, 21, 10, 0, 0),
    )
    sqlite_db.commit()

    overview = get_market_overview(sqlite_db)

    assert overview.market_sentiment == "insufficient_data"
    assert overview.confidence_label == "insufficient"
    assert overview.indexes == []
    assert overview.top_movers == []
    assert overview.signal_summary == []
    assert overview.commentary.startswith("Insufficient evidence")
