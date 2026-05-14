import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import JSON, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
from backend.app.db.base import Base
from backend.app.models.asset import Asset
from backend.app.models.asset_signal import AssetSignal
from backend.app.models.enums import SignalLabel
from backend.app.models.price_history import PriceHistory
from backend.app.services.signal_service import (
    CARDMARKET_DISPERSION_THRESHOLD,
    CM_SOURCES,
    compute_cardmarket_delta,
)


def _coerce():
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


@contextmanager
def _db():
    _coerce()
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)


def _make_asset(session):
    asset = Asset(
        id=uuid.uuid4(),
        asset_class="tcg",
        category="yugioh",
        game="yugioh",
        name="Test YGO Card",
        set_name="POTE",
        card_number="001",
        language="EN",
        variant="SR",
        external_id=f"test-{uuid.uuid4()}",
        metadata_json={},
    )
    session.add(asset)
    session.commit()
    return asset


def _add_cm_row(session, asset_id, source, price, captured_at=None):
    row = PriceHistory(
        id=uuid.uuid4(),
        asset_id=asset_id,
        source=source,
        currency="EUR",
        price=Decimal(str(price)),
        captured_at=captured_at or datetime.now(UTC),
        market_segment="raw",
    )
    session.add(row)
    session.commit()
    return row


def test_cardmarket_delta_positive_breakout():
    now = datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
    with _db() as db:
        asset = _make_asset(db)
        _add_cm_row(db, asset.id, "cardmarket_avg7", "11.0", now)
        _add_cm_row(db, asset.id, "cardmarket_avg30", "10.0", now)

        delta, ctx = compute_cardmarket_delta(db, asset.id, now=now)

    assert delta == Decimal("10.00")
    assert ctx["current_price"] == 11.0
    assert ctx["baseline_price"] == 10.0


def test_cardmarket_delta_no_data_returns_none():
    now = datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
    with _db() as db:
        asset = _make_asset(db)

        delta, ctx = compute_cardmarket_delta(db, asset.id, now=now)

    assert delta is None
    assert ctx["reason"] == "no_cardmarket_data"


def test_cardmarket_delta_missing_avg30_returns_none():
    now = datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
    with _db() as db:
        asset = _make_asset(db)
        _add_cm_row(db, asset.id, "cardmarket_avg7", "11.0", now)

        delta, ctx = compute_cardmarket_delta(db, asset.id, now=now)

    assert delta is None
    assert ctx["reason"] == "no_baseline"


def test_cardmarket_dispersion_gate_triggers_on_high_avg1():
    now = datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
    with _db() as db:
        asset = _make_asset(db)
        _add_cm_row(db, asset.id, "cardmarket_avg7", "5.0", now)
        _add_cm_row(db, asset.id, "cardmarket_avg30", "4.8", now)
        _add_cm_row(db, asset.id, "cardmarket_avg1", "20.0", now)

        delta, ctx = compute_cardmarket_delta(db, asset.id, now=now)

    assert CARDMARKET_DISPERSION_THRESHOLD == Decimal(999)
    assert delta is not None
    assert "dispersion_ratio" in ctx


def test_cardmarket_dispersion_gate_passes_on_low_avg1():
    now = datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
    with _db() as db:
        asset = _make_asset(db)
        _add_cm_row(db, asset.id, "cardmarket_avg7", "5.0", now)
        _add_cm_row(db, asset.id, "cardmarket_avg30", "4.8", now)
        _add_cm_row(db, asset.id, "cardmarket_avg1", "5.3", now)

        delta, _ctx = compute_cardmarket_delta(db, asset.id, now=now)

    assert delta is not None


def test_cardmarket_bulk_floor_gate():
    now = datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
    with _db() as db:
        asset = _make_asset(db)
        _add_cm_row(db, asset.id, "cardmarket_avg7", "0.25", now)
        _add_cm_row(db, asset.id, "cardmarket_avg30", "0.20", now)

        delta, ctx = compute_cardmarket_delta(db, asset.id, now=now)

    assert delta is None
    assert ctx["reason"] == "bulk_baseline_price"


def test_cardmarket_zero_baseline_guard():
    now = datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
    with _db() as db:
        asset = _make_asset(db)
        _add_cm_row(db, asset.id, "cardmarket_avg7", "5.0", now)
        _add_cm_row(db, asset.id, "cardmarket_avg30", "0.0", now)

        delta, ctx = compute_cardmarket_delta(db, asset.id, now=now)

    assert delta is None
    assert ctx["reason"] in ("zero_baseline", "bulk_baseline_price")


def test_cm_sources_constant_contains_expected_values():
    assert "cardmarket_avg7" in CM_SOURCES
    assert "cardmarket_avg30" in CM_SOURCES
    assert "cardmarket_avg1" in CM_SOURCES


def test_ingest_304_preserves_etag(monkeypatch):
    """When download() returns None (HTTP 304), catalog_etag must be carried
    forward so the next run can still send If-None-Match and get another 304."""
    from unittest.mock import patch
    from backend.app.ingestion.cardmarket import ingest_cardmarket_ygo

    with _db() as db:
        with patch("backend.app.ingestion.cardmarket.CardmarketCatalog.download", return_value=None):
            result = ingest_cardmarket_ygo(db, last_etag="W/\"abc123\"")

    assert result.skipped_not_modified is True
    assert result.catalog_etag == "W/\"abc123\""
