from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import JSON, create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
from backend.app.db.base import Base
from backend.app.models.daily_market_report import DailyMarketReport
from backend.app.schemas.market import (
    MarketIndexResponse,
    MarketOverviewResponse,
    MarketSignalSummaryResponse,
    MarketTopMoverResponse,
)
from backend.app.services.daily_market_report_service import (
    create_daily_market_report,
    get_daily_market_report_by_date,
    get_latest_daily_market_report,
)


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


def _overview(*, sentiment: str = "bullish", commentary: str = "Market is bullish.") -> MarketOverviewResponse:
    return MarketOverviewResponse(
        generated_at=datetime(2026, 7, 21, 10, 0, tzinfo=UTC),
        market_sentiment=sentiment,
        confidence_label="medium",
        indexes=[
            MarketIndexResponse(
                game="pokemon",
                label="Pokemon Market",
                change_pct=Decimal("12.34"),
                direction="up",
                observed_assets=4,
                current_assets=6,
                confidence_label="medium",
            )
        ],
        top_movers=[
            MarketTopMoverResponse(
                asset_id="11111111-1111-1111-1111-111111111111",
                name="Charizard",
                game="pokemon",
                set_name="Base Set",
                latest_price=Decimal("120.00"),
                previous_price=Decimal("100.00"),
                percent_change=Decimal("20.00"),
                absolute_change=Decimal("20.00"),
                direction="up",
            )
        ],
        signal_summary=[MarketSignalSummaryResponse(label="BREAKOUT", count=1, average_confidence=Decimal("88.00"))],
        commentary=commentary,
        evidence=["market_segment=raw", "active price source: sample_seed"],
    )


def test_create_daily_market_report_persists_overview_snapshot(sqlite_db, mocker):
    mocker.patch(
        "backend.app.services.daily_market_report_service.get_market_overview",
        return_value=_overview(),
    )

    report = create_daily_market_report(
        sqlite_db,
        report_date=date(2026, 7, 21),
        now=datetime(2026, 7, 21, 10, 30, tzinfo=UTC),
    )

    assert report.report_date == date(2026, 7, 21)
    assert report.title == "Flashcard Planet Daily - 2026-07-21"
    assert report.market_sentiment == "bullish"
    assert report.confidence_label == "medium"
    assert report.overview.indexes[0].label == "Pokemon Market"
    assert report.overview.top_movers[0].name == "Charizard"
    assert report.evidence == ["market_segment=raw", "active price source: sample_seed"]

    stored = sqlite_db.scalar(select(DailyMarketReport))
    assert stored is not None
    assert stored.report_date == date(2026, 7, 21)
    assert stored.overview_json["market_sentiment"] == "bullish"


def test_create_daily_market_report_upserts_same_report_date(sqlite_db, mocker):
    mocker.patch(
        "backend.app.services.daily_market_report_service.get_market_overview",
        return_value=_overview(commentary="First summary."),
    )
    first = create_daily_market_report(sqlite_db, report_date=date(2026, 7, 21))

    mocker.patch(
        "backend.app.services.daily_market_report_service.get_market_overview",
        return_value=_overview(sentiment="neutral", commentary="Updated summary."),
    )
    second = create_daily_market_report(sqlite_db, report_date=date(2026, 7, 21))

    assert second.id == first.id
    assert second.market_sentiment == "neutral"
    assert second.summary == "Updated summary."
    assert sqlite_db.scalar(select(func.count(DailyMarketReport.id))) == 1


def test_get_latest_and_dated_daily_market_report(sqlite_db, mocker):
    mocker.patch(
        "backend.app.services.daily_market_report_service.get_market_overview",
        return_value=_overview(),
    )
    older = create_daily_market_report(sqlite_db, report_date=date(2026, 7, 20))
    latest = create_daily_market_report(sqlite_db, report_date=date(2026, 7, 21))

    assert get_latest_daily_market_report(sqlite_db).id == latest.id
    assert get_daily_market_report_by_date(sqlite_db, date(2026, 7, 20)).id == older.id
    assert get_daily_market_report_by_date(sqlite_db, date(2026, 7, 19)) is None
