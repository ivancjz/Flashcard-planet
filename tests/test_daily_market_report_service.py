from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import JSON, create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
import backend.app.services.catalyst_service as catalyst_service
import backend.app.services.daily_market_report_service as daily_market_report_service
from backend.app.db.base import Base
from backend.app.models.daily_market_report import DailyMarketReport
from backend.app.models.daily_report_intelligence import DailyReportIntelligence
from backend.app.models.predictions import MarketEvent
from backend.app.schemas.catalyst import CatalystResponse
from backend.app.schemas.daily_report_intelligence import (
    DailyReportIntelligenceResponse,
)
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
    list_daily_market_reports,
)
from backend.app.services.daily_report_commentary import PROMPT_VERSION
from backend.app.services.daily_report_evidence import (
    build_daily_report_evidence_bundle,
    evidence_hash,
)


AS_OF = datetime(2026, 7, 21, 10, 30, tzinfo=UTC)


def _coerce_postgres_types_for_sqlite() -> list[tuple[object, object]]:
    original_types = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                original_types.append((column, column.type))
                column.type = JSON()
    return original_types


@pytest.fixture
def sqlite_db():
    original_types = _coerce_postgres_types_for_sqlite()
    engine = None
    try:
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        session_local = sessionmaker(
            bind=engine,
            autoflush=False,
            autocommit=False,
            future=True,
        )
        with session_local() as db:
            yield db
    finally:
        try:
            if engine is not None:
                Base.metadata.drop_all(engine)
        finally:
            try:
                if engine is not None:
                    engine.dispose()
            finally:
                for column, original_type in original_types:
                    column.type = original_type


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


def _uuid(value: int) -> UUID:
    return UUID(hex=f"b{value:031x}")


def _event(**overrides) -> MarketEvent:
    data = {
        "id": _uuid(1),
        "event_date": AS_OF - timedelta(days=1),
        "event_type": "RELEASE",
        "description": "Verified catalyst snapshot",
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


def _persist_events(sqlite_db, *events: MarketEvent) -> None:
    sqlite_db.add_all(events)
    sqlite_db.commit()
    sqlite_db.expunge_all()


def test_daily_report_selector_keeps_active_and_30_day_upcoming_boundary(sqlite_db):
    active = _event(id=_uuid(10), event_date=AS_OF - timedelta(days=1))
    upcoming_at_horizon = _event(
        id=_uuid(11),
        event_date=AS_OF + timedelta(days=30),
    )
    expired = _event(
        id=_uuid(12),
        event_date=AS_OF - timedelta(days=15, microseconds=1),
    )
    upcoming_after_horizon = _event(
        id=_uuid(13),
        event_date=AS_OF + timedelta(days=30, microseconds=1),
    )
    _persist_events(
        sqlite_db,
        active,
        upcoming_at_horizon,
        expired,
        upcoming_after_horizon,
    )

    selected = catalyst_service.select_daily_report_catalysts(
        sqlite_db,
        as_of=AS_OF.replace(tzinfo=None),
        limit=10,
    )

    assert [item.id for item in selected] == [_uuid(10), _uuid(11)]
    assert [item.status for item in selected] == ["active", "upcoming"]


def test_daily_report_selector_returns_at_most_five(sqlite_db):
    _persist_events(
        sqlite_db,
        *[
            _event(id=_uuid(20 + index), impact_score=100 - index)
            for index in range(6)
        ],
    )

    selected = catalyst_service.select_daily_report_catalysts(
        sqlite_db,
        as_of=AS_OF,
    )

    assert len(selected) == 5
    assert [item.id for item in selected] == [_uuid(value) for value in range(20, 25)]


def test_daily_report_selector_returns_empty_list_for_empty_registry(sqlite_db):
    assert catalyst_service.select_daily_report_catalysts(
        sqlite_db,
        as_of=AS_OF,
    ) == []


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


def test_create_daily_market_report_persists_complete_catalyst_snapshot(sqlite_db, mocker):
    catalyst = _event(description="Source catalyst must stay out of commentary")
    catalyst_id = catalyst.id
    catalyst_description = catalyst.description
    _persist_events(sqlite_db, catalyst)
    mocker.patch(
        "backend.app.services.daily_market_report_service.get_market_overview",
        return_value=_overview(commentary="Overview-only summary."),
    )

    report = create_daily_market_report(
        sqlite_db,
        report_date=date(2026, 7, 21),
        now=AS_OF,
    )

    assert len(report.catalysts) == 1
    assert report.catalysts[0].id == catalyst_id
    assert set(report.catalysts[0].model_dump()) == set(CatalystResponse.model_fields)
    assert report.summary == "Overview-only summary."
    assert report.overview.commentary == "Overview-only summary."
    assert catalyst_description not in report.summary

    stored = sqlite_db.scalar(select(DailyMarketReport))
    assert stored is not None
    assert stored.catalysts_json == [
        report.catalysts[0].model_dump(mode="json")
    ]


def test_create_daily_market_report_stores_and_returns_empty_catalysts(sqlite_db, mocker):
    mocker.patch(
        "backend.app.services.daily_market_report_service.get_market_overview",
        return_value=_overview(),
    )

    report = create_daily_market_report(sqlite_db, now=AS_OF)

    stored = sqlite_db.scalar(select(DailyMarketReport))
    assert stored is not None
    assert report.catalysts == []
    assert stored.catalysts_json == []


def test_none_stored_catalyst_snapshot_maps_to_empty_list(sqlite_db, mocker):
    mocker.patch(
        "backend.app.services.daily_market_report_service.get_market_overview",
        return_value=_overview(),
    )
    create_daily_market_report(sqlite_db, now=AS_OF)
    stored = sqlite_db.scalar(select(DailyMarketReport))
    stored.catalysts_json = None

    assert daily_market_report_service._response_from_row(stored).catalysts == []


def test_published_report_catalysts_do_not_change_with_source_event(sqlite_db, mocker):
    catalyst = _event(
        description="Original catalyst",
        source_url="https://example.com/original",
    )
    catalyst_id = catalyst.id
    _persist_events(sqlite_db, catalyst)
    mocker.patch(
        "backend.app.services.daily_market_report_service.get_market_overview",
        return_value=_overview(),
    )
    published = create_daily_market_report(sqlite_db, now=AS_OF)
    snapshot = published.catalysts[0].model_dump(mode="json")

    source = sqlite_db.get(MarketEvent, catalyst_id)
    source.description = "Edited after publication"
    source.source_url = "https://example.com/edited"
    sqlite_db.commit()
    sqlite_db.expire_all()

    stored_report = get_daily_market_report_by_date(sqlite_db, AS_OF.date())

    assert stored_report is not None
    assert stored_report.catalysts[0].model_dump(mode="json") == snapshot


def test_incomplete_stored_catalyst_snapshot_fails_validation(sqlite_db, mocker):
    mocker.patch(
        "backend.app.services.daily_market_report_service.get_market_overview",
        return_value=_overview(),
    )
    create_daily_market_report(sqlite_db, now=AS_OF)
    stored = sqlite_db.scalar(select(DailyMarketReport))
    stored.catalysts_json = [{"description": "incomplete"}]
    sqlite_db.commit()
    sqlite_db.expire_all()

    with pytest.raises(ValidationError):
        get_daily_market_report_by_date(sqlite_db, AS_OF.date())


@pytest.mark.parametrize(
    "malformed_snapshot",
    [{}, "", 0, False],
    ids=["object", "string", "integer", "boolean"],
)
def test_malformed_outer_catalyst_snapshot_fails_validation(
    sqlite_db,
    mocker,
    malformed_snapshot,
):
    mocker.patch(
        "backend.app.services.daily_market_report_service.get_market_overview",
        return_value=_overview(),
    )
    create_daily_market_report(sqlite_db, now=AS_OF)
    stored = sqlite_db.scalar(select(DailyMarketReport))
    stored.catalysts_json = malformed_snapshot
    sqlite_db.commit()
    sqlite_db.expire_all()

    with pytest.raises(ValidationError):
        get_daily_market_report_by_date(sqlite_db, AS_OF.date())


@pytest.mark.parametrize("existing", [False, True], ids=["new", "existing"])
def test_selector_failure_does_not_publish_or_commit_report(
    sqlite_db,
    mocker,
    existing,
):
    report_date = AS_OF.date()
    if existing:
        sqlite_db.add(
            DailyMarketReport(
                report_date=report_date,
                generated_at=AS_OF - timedelta(days=1),
                status="draft",
                title="Original title",
                market_sentiment="neutral",
                confidence_label="low",
                summary="Original summary",
                overview_json=_overview().model_dump(mode="json"),
                evidence_json=["original evidence"],
                catalysts_json=[],
            )
        )
        sqlite_db.commit()

    add_spy = mocker.spy(sqlite_db, "add")
    commit_spy = mocker.spy(sqlite_db, "commit")
    mocker.patch(
        "backend.app.services.daily_market_report_service.get_market_overview",
        return_value=_overview(commentary="Replacement summary"),
    )
    mocker.patch(
        "backend.app.services.daily_market_report_service.select_daily_report_catalysts",
        side_effect=RuntimeError("catalyst selection failed"),
        create=True,
    )

    with pytest.raises(RuntimeError, match="catalyst selection failed"):
        create_daily_market_report(sqlite_db, report_date=report_date, now=AS_OF)

    add_spy.assert_not_called()
    commit_spy.assert_not_called()
    rows = sqlite_db.scalars(select(DailyMarketReport)).all()
    if existing:
        assert len(rows) == 1
        assert rows[0].status == "draft"
        assert rows[0].title == "Original title"
        assert rows[0].summary == "Original summary"
        assert rows[0].catalysts_json == []
    else:
        assert rows == []


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


def test_list_daily_market_reports_returns_descending_paginated_page(sqlite_db, mocker):
    mocker.patch(
        "backend.app.services.daily_market_report_service.get_market_overview",
        return_value=_overview(),
    )
    for report_date in (date(2026, 7, 20), date(2026, 7, 21), date(2026, 7, 22)):
        create_daily_market_report(sqlite_db, report_date=report_date)

    page = list_daily_market_reports(sqlite_db, limit=2, offset=1)

    assert page.total == 3
    assert page.limit == 2
    assert page.offset == 1
    assert [report.report_date for report in page.reports] == [
        date(2026, 7, 21),
        date(2026, 7, 20),
    ]


def _persist_report_row(
    sqlite_db,
    *,
    report_date: date = date(2026, 7, 21),
) -> DailyMarketReport:
    row = DailyMarketReport(
        id=_uuid(report_date.day + 100),
        report_date=report_date,
        generated_at=AS_OF,
        status="published",
        title=f"Flashcard Planet Daily - {report_date.isoformat()}",
        market_sentiment="bullish",
        confidence_label="medium",
        summary="Market is bullish.",
        overview_json=_overview().model_dump(mode="json"),
        evidence_json=["market_segment=raw"],
        catalysts_json=[],
        created_at=AS_OF,
        updated_at=AS_OF,
    )
    sqlite_db.add(row)
    sqlite_db.commit()
    return row


def _persist_intelligence(
    sqlite_db,
    report: DailyMarketReport,
    *,
    status: str = "published",
    digest: str | None = None,
) -> DailyReportIntelligence:
    current_digest = evidence_hash(build_daily_report_evidence_bundle(report))
    row = DailyReportIntelligence(
        id=_uuid(report.report_date.day + 200),
        report_id=report.id,
        evidence_hash=digest or current_digest,
        prompt_version=PROMPT_VERSION,
        status=status,
        headline=(
            "Pokemon market breadth improved"
            if status == "published"
            else None
        ),
        commentary=(
            "Pokemon Market moved 12.34% in the captured snapshot."
            if status == "published"
            else "Insufficient evidence."
            if status == "insufficient_evidence"
            else None
        ),
        risk_summary=(
            "Coverage includes 4 observed assets."
            if status == "published"
            else None
        ),
        key_observations_json=(
            ["Charizard moved 20%."] if status == "published" else []
        ),
        evidence_refs_json=(
            {
                "headline": ["index:pokemon"],
                "commentary": ["index:pokemon"],
                "key_observations": [
                    ["mover:11111111-1111-1111-1111-111111111111"]
                ],
                "risk_summary": ["index:pokemon"],
            }
            if status == "published"
            else {}
        ),
        provider="openai" if status == "published" else None,
        model="internal-model" if status == "published" else None,
        attempt_count=1 if status == "published" else 0,
        error_code="internal-only-error" if status == "failed" else None,
        generated_at=AS_OF if status == "published" else None,
        created_at=AS_OF,
        updated_at=AS_OF,
    )
    sqlite_db.add(row)
    sqlite_db.commit()
    return row


def test_matching_published_intelligence_is_public(sqlite_db):
    report_row = _persist_report_row(sqlite_db)
    _persist_intelligence(sqlite_db, report_row)

    report = get_latest_daily_market_report(sqlite_db)

    assert report is not None
    assert report.intelligence.status == "published"
    assert report.intelligence.headline == "Pokemon market breadth improved"
    assert report.intelligence.headline_evidence_refs == ["index:pokemon"]
    assert report.intelligence.commentary_evidence_refs == ["index:pokemon"]
    assert report.intelligence.risk_evidence_refs == ["index:pokemon"]
    assert report.intelligence.key_observations[0].text == "Charizard moved 20%."
    assert report.intelligence.evidence_refs == [
        "index:pokemon",
        "mover:11111111-1111-1111-1111-111111111111",
    ]
    assert [
        item.source_record_id
        for item in report.intelligence.evidence_catalog
    ] == ["pokemon", "11111111-1111-1111-1111-111111111111"]
    assert all(
        item.target_anchor.startswith("evidence-")
        for item in report.intelligence.evidence_catalog
    )
    payload = report.intelligence.model_dump()
    assert not (
        {
            "provider",
            "model",
            "attempt_count",
            "error_code",
            "evidence_hash",
            "prompt_version",
        }
        & payload.keys()
    )
    assert all(
        not ({"facts", "source_url"} & item.keys())
        for item in report.intelligence.model_dump()["evidence_catalog"]
    )


@pytest.mark.parametrize(
    ("status", "digest"),
    [
        ("published", "f" * 64),
        ("failed", None),
        ("pending", None),
    ],
)
def test_stale_pending_or_failed_intelligence_is_publicly_unavailable(
    sqlite_db,
    status,
    digest,
):
    report_row = _persist_report_row(sqlite_db)
    _persist_intelligence(
        sqlite_db,
        report_row,
        status=status,
        digest=digest,
    )

    report = get_latest_daily_market_report(sqlite_db)

    assert report is not None
    assert (
        report.intelligence.model_dump()
        == DailyReportIntelligenceResponse().model_dump()
    )


def test_insufficient_intelligence_has_exact_public_message(sqlite_db):
    report_row = _persist_report_row(sqlite_db)
    _persist_intelligence(
        sqlite_db,
        report_row,
        status="insufficient_evidence",
    )

    report = get_latest_daily_market_report(sqlite_db)

    assert report is not None
    assert report.intelligence.status == "insufficient_evidence"
    assert report.intelligence.commentary == "Insufficient evidence."
    assert report.intelligence.evidence_refs == []
    assert report.intelligence.evidence_catalog == []


def test_history_bulk_loads_intelligence_once(sqlite_db, mocker):
    reports = [
        _persist_report_row(
            sqlite_db,
            report_date=date(2026, 7, report_day),
        )
        for report_day in (19, 20, 21)
    ]
    loader = mocker.spy(
        daily_market_report_service,
        "load_intelligence_candidates",
    )

    page = list_daily_market_reports(sqlite_db, limit=3, offset=0)

    assert len(page.reports) == 3
    loader.assert_called_once()
    assert set(loader.call_args.args[1]) == {report.id for report in reports}
