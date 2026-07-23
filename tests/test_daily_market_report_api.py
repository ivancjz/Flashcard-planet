from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from backend.app.api.deps import get_database
from backend.app.api.router import api_router
from backend.app.api.routes.market import router as market_router
from backend.app.schemas.daily_market_report import (
    DailyMarketReportListResponse,
    DailyMarketReportResponse,
)
from backend.app.schemas.daily_report_intelligence import (
    DailyReportEvidenceCatalogItemResponse,
    DailyReportIntelligenceResponse,
)
from backend.app.schemas.market import MarketOverviewResponse


def _report_response() -> DailyMarketReportResponse:
    overview = MarketOverviewResponse(
        generated_at=datetime(2026, 7, 21, 10, 0, tzinfo=UTC),
        market_sentiment="bullish",
        confidence_label="medium",
        indexes=[],
        top_movers=[],
        signal_summary=[],
        commentary="Market is bullish.",
        evidence=["market_segment=raw"],
    )
    return DailyMarketReportResponse(
        id=UUID("22222222-2222-2222-2222-222222222222"),
        report_date=date(2026, 7, 21),
        generated_at=datetime(2026, 7, 21, 10, 30, tzinfo=UTC),
        status="published",
        title="Flashcard Planet Daily - 2026-07-21",
        market_sentiment="bullish",
        confidence_label="medium",
        summary="Market is bullish.",
        overview=overview,
        evidence=["market_segment=raw"],
        catalysts=[],
    )


def _client(db=object()) -> tuple[FastAPI, TestClient, object]:
    app = FastAPI()
    app.include_router(market_router, prefix="/api/v1")
    app.dependency_overrides[get_database] = lambda: db
    return app, TestClient(app), db


def test_public_daily_market_report_routes_are_read_only():
    report_routes = [
        route
        for route in api_router.routes
        if isinstance(route, APIRoute)
        and route.path.startswith("/api/v1/market/daily-report")
    ]

    assert "/api/v1/market/daily-report/generate" not in {
        route.path for route in report_routes
    }
    assert report_routes
    assert all(route.methods == {"GET"} for route in report_routes)


def test_latest_daily_market_report_route(mocker):
    app, client, db = _client()
    service = mocker.patch(
        "backend.app.api.routes.market.get_latest_daily_market_report",
        return_value=_report_response(),
    )

    response = client.get("/api/v1/market/daily-report/latest")

    assert response.status_code == 200
    assert response.json()["report_date"] == "2026-07-21"
    assert response.json()["catalysts"] == []
    assert response.json()["intelligence"]["status"] == "unavailable"
    service.assert_called_once_with(db)
    app.dependency_overrides.clear()


def test_latest_route_preserves_field_scoped_citations_without_private_metadata(
    mocker,
):
    app, client, db = _client()
    intelligence = DailyReportIntelligenceResponse(
        status="published",
        headline="Pokemon market breadth improved.",
        headline_evidence_refs=["index:pokemon"],
        commentary="Charizard was the leading observed mover.",
        commentary_evidence_refs=[
            "mover:11111111-1111-1111-1111-111111111111"
        ],
        risk_summary="Coverage remains limited to the captured snapshot.",
        risk_evidence_refs=["report:evidence:1"],
        evidence_refs=[
            "index:pokemon",
            "mover:11111111-1111-1111-1111-111111111111",
            "report:evidence:1",
        ],
        evidence_catalog=[
            DailyReportEvidenceCatalogItemResponse(
                id="index:pokemon",
                kind="index",
                label="Pokemon Market",
                source_record_id="pokemon",
                target_anchor="market-indexes",
            ),
            DailyReportEvidenceCatalogItemResponse(
                id="mover:11111111-1111-1111-1111-111111111111",
                kind="mover",
                label="Charizard",
                source_record_id="11111111-1111-1111-1111-111111111111",
                target_anchor="top-movers",
            ),
            DailyReportEvidenceCatalogItemResponse(
                id="report:evidence:1",
                kind="report_evidence",
                label="Market segment raw",
                source_record_id="market_segment=raw",
                target_anchor="report-evidence",
            ),
        ],
        generated_at=datetime(2026, 7, 21, 10, 15, tzinfo=UTC),
    )
    report = _report_response().model_copy(
        update={"intelligence": intelligence}
    )
    mocker.patch(
        "backend.app.api.routes.market.get_latest_daily_market_report",
        return_value=report,
    )

    response = client.get("/api/v1/market/daily-report/latest")

    assert response.status_code == 200
    payload = response.json()["intelligence"]
    assert payload["headline_evidence_refs"] == ["index:pokemon"]
    assert payload["commentary_evidence_refs"] == [
        "mover:11111111-1111-1111-1111-111111111111"
    ]
    assert payload["risk_evidence_refs"] == ["report:evidence:1"]
    assert payload["evidence_catalog"][2]["source_record_id"] == (
        "market_segment=raw"
    )
    assert {
        "provider",
        "model",
        "prompt_version",
        "error_code",
    }.isdisjoint(payload)
    app.dependency_overrides.clear()


def test_daily_market_report_history_route(mocker):
    app, client, db = _client()
    service = mocker.patch(
        "backend.app.api.routes.market.list_daily_market_reports",
        create=True,
        return_value=DailyMarketReportListResponse(
            reports=[_report_response()],
            total=1,
            limit=20,
            offset=10,
        ),
    )

    response = client.get("/api/v1/market/daily-report?limit=20&offset=10")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["reports"][0]["report_date"] == "2026-07-21"
    assert response.json()["reports"][0]["catalysts"] == []
    assert (
        response.json()["reports"][0]["intelligence"]["status"]
        == "unavailable"
    )
    service.assert_called_once_with(db, limit=20, offset=10)
    app.dependency_overrides.clear()


def test_daily_market_report_history_route_validates_pagination():
    app, client, _db = _client()

    assert client.get("/api/v1/market/daily-report?limit=0").status_code == 422
    assert client.get("/api/v1/market/daily-report?limit=101").status_code == 422
    assert client.get("/api/v1/market/daily-report?offset=-1").status_code == 422
    app.dependency_overrides.clear()


def test_dated_daily_market_report_route_returns_404_when_missing(mocker):
    app, client, db = _client()
    service = mocker.patch(
        "backend.app.api.routes.market.get_daily_market_report_by_date",
        return_value=None,
    )

    response = client.get("/api/v1/market/daily-report/2026-07-19")

    assert response.status_code == 404
    assert response.json()["detail"] == "No daily market report found for 2026-07-19."
    service.assert_called_once_with(db, date(2026, 7, 19))
    app.dependency_overrides.clear()


def test_api_router_registers_daily_market_report_routes():
    paths = [route.path for route in api_router.routes]

    assert "/api/v1/market/daily-report" in paths
    assert "/api/v1/market/daily-report/latest" in paths
    assert "/api/v1/market/daily-report/{report_date}" in paths
