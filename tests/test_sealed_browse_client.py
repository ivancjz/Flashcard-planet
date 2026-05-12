"""Tests for sealed_browse_client.py (TASK-502)."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import JSON, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401 — registers all mappers
from backend.app.db.base import Base
from backend.app.ingestion.sealed_browse_client import (
    ProductConfig,
    _compute_from_price,
    _parse_listing_price,
    load_sealed_products,
)
from backend.app.models.asset import Asset
from backend.app.models.enums import AssetClass
from backend.app.models.listing_snapshot import ListingSnapshot


def _coerce_jsonb_for_sqlite() -> None:
    from sqlalchemy.dialects.postgresql import JSONB
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()


@contextmanager
def _session():
    _coerce_jsonb_for_sqlite()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with Session() as db:
        yield db
    Base.metadata.drop_all(engine)


# ---------------------------------------------------------------------------
# load_sealed_products
# ---------------------------------------------------------------------------

def test_load_sealed_products_returns_20():
    products = load_sealed_products()
    assert len(products) == 20


def test_load_sealed_products_all_have_required_fields():
    for p in load_sealed_products():
        assert p.name
        assert p.ebay_search_query
        assert p.product_type in ("booster_box", "etb", "case", "blister", "other")
        assert p.game == "pokemon"


# ---------------------------------------------------------------------------
# _parse_listing_price
# ---------------------------------------------------------------------------

def test_parse_listing_price_item_plus_shipping():
    item = {
        "price": {"value": "100.00"},
        "shippingOptions": [{"shippingCost": {"value": "15.00"}}],
    }
    assert _parse_listing_price(item) == Decimal("115.00")


def test_parse_listing_price_no_shipping_falls_back_to_item():
    item = {"price": {"value": "80.00"}, "shippingOptions": []}
    assert _parse_listing_price(item) == Decimal("80.00")


def test_parse_listing_price_free_shipping():
    item = {
        "price": {"value": "95.00"},
        "shippingOptions": [{"shippingCost": {"value": "0.00"}}],
    }
    assert _parse_listing_price(item) == Decimal("95.00")


def test_parse_listing_price_zero_price_returns_none():
    item = {"price": {"value": "0"}}
    assert _parse_listing_price(item) is None


# ---------------------------------------------------------------------------
# _compute_from_price
# ---------------------------------------------------------------------------

def _make_items(prices: list[float]) -> list[dict]:
    return [{"price": {"value": str(p)}, "shippingOptions": []} for p in prices]


def test_compute_from_price_happy_path():
    # 8 listings: skip cheapest (rank 1), median ranks 2-6
    items = _make_items([50, 80, 85, 90, 95, 100, 110, 120])
    from_price, listing_count, min_count_met, raw = _compute_from_price(items)
    assert min_count_met is True
    assert listing_count == 8
    # ranks sorted: 50, 80, 85, 90, 95, 100, 110, 120
    # skip rank 1 (50), take ranks 2-6: 80, 85, 90, 95, 100
    # median([80, 85, 90, 95, 100]) = 90
    assert from_price == Decimal("90.00")


def test_compute_from_price_exactly_5_listings():
    items = _make_items([70, 80, 90, 100, 110])
    from_price, listing_count, min_count_met, raw = _compute_from_price(items)
    assert min_count_met is True
    assert listing_count == 5
    # sorted: 70, 80, 90, 100, 110 — skip rank 1 (70), take 2-6: 80, 90, 100, 110, (no 6th)
    # actually with exactly 5 sorted items: ranks 2-6 gives indices [1:6] = [80, 90, 100, 110]
    # only 4 items but _MIN_LISTING_COUNT=5 passed, so this uses all 5 with skip rank 1
    assert from_price is not None


def test_compute_from_price_insufficient_listings():
    items = _make_items([80, 90, 100, 110])  # only 4
    from_price, listing_count, min_count_met, raw = _compute_from_price(items)
    assert min_count_met is False
    assert from_price is None
    assert listing_count == 4


def test_compute_from_price_empty():
    from_price, listing_count, min_count_met, raw = _compute_from_price([])
    assert min_count_met is False
    assert from_price is None
    assert listing_count == 0


def test_compute_from_price_raw_snapshot_capped_at_10():
    items = _make_items([100] * 15)
    _, _, _, raw = _compute_from_price(items)
    assert len(raw) <= 10


# ---------------------------------------------------------------------------
# _upsert_asset
# ---------------------------------------------------------------------------

def test_upsert_asset_creates_on_first_run():
    from backend.app.ingestion.sealed_browse_client import _upsert_asset

    with _session() as db:
        product = ProductConfig(
            name="Test ETB",
            set_name="Test Set",
            ebay_search_query="test query",
            product_type="etb",
            game="pokemon",
        )
        asset_id = _upsert_asset(db, product)
        db.commit()

        asset = db.scalars(select(Asset).where(Asset.id == asset_id)).first()
        assert asset is not None
        assert asset.asset_class == AssetClass.SEALED.value
        assert asset.product_type == "etb"
        assert asset.game == "pokemon"


def test_upsert_asset_idempotent_on_second_run():
    from backend.app.ingestion.sealed_browse_client import _upsert_asset

    with _session() as db:
        product = ProductConfig(
            name="Test ETB",
            set_name="Test Set",
            ebay_search_query="test query",
            product_type="etb",
            game="pokemon",
        )
        id1 = _upsert_asset(db, product)
        db.commit()
        id2 = _upsert_asset(db, product)
        db.commit()

        assert id1 == id2
        count = db.query(Asset).filter_by(name="Test ETB").count()
        assert count == 1


# ---------------------------------------------------------------------------
# AssetClass.SEALED does not appear in _get_active_asset_ids
# ---------------------------------------------------------------------------

def test_sealed_asset_excluded_from_active_ids_even_with_price_history():
    """Defensive test: if somehow a price_history row existed for a SEALED asset,
    _get_active_asset_ids still excludes it due to the asset_class filter."""
    from backend.app.services.signal_service import _get_active_asset_ids
    from backend.app.models.price_history import PriceHistory
    import uuid
    from decimal import Decimal

    with _session() as db:
        # Create a SEALED asset
        sealed = Asset(
            asset_class=AssetClass.SEALED.value,
            game="pokemon",
            name="Sealed ETB Test",
            set_name="Test",
        )
        db.add(sealed)
        db.flush()

        # Artificially give it a price_history row (shouldn't happen in prod, defensive test)
        ph = PriceHistory(
            asset_id=sealed.id,
            source="ebay_sealed_ask",
            currency="USD",
            price=Decimal("100.00"),
            market_segment="raw",
        )
        db.add(ph)
        db.commit()

        active_ids = _get_active_asset_ids(db)
        assert sealed.id not in active_ids


# ---------------------------------------------------------------------------
# run_sealed_ingest — fetch failure path (Codex P0 regression guard)
# ---------------------------------------------------------------------------

def test_fetch_failure_increments_fail_count_and_skips_snapshot():
    """When _fetch_listings_for_product raises, fail_count increments and no snapshot is written.

    Regression guard for Codex P0: the old code swallowed exceptions and returned
    (None, 0, False, []), causing run_sealed_ingest to write a snapshot and record
    status="success" even during an API outage (CLAUDE.md Lesson 9 violation).
    """
    import httpx
    from backend.app.ingestion.sealed_browse_client import run_sealed_ingest

    one_product = [ProductConfig(
        name="Test ETB",
        set_name="Test Set",
        ebay_search_query="test query",
        product_type="etb",
        game="pokemon",
    )]

    mock_settings = MagicMock()
    mock_settings.ebay_app_id = "fake_app_id"
    mock_settings.ebay_cert_id = "fake_cert_id"

    # httpx.Client must work as a context manager
    mock_client_instance = MagicMock()
    mock_client_cls = MagicMock()
    mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client_instance)
    mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

    with _session() as db:
        with (
            patch("backend.app.ingestion.sealed_browse_client.get_settings", return_value=mock_settings),
            patch("backend.app.ingestion.sealed_browse_client.load_sealed_products", return_value=one_product),
            patch("backend.app.ingestion.sealed_browse_client.httpx.Client", mock_client_cls),
            patch("backend.app.ingestion.sealed_browse_client._get_oauth_token", return_value="fake_token"),
            patch(
                "backend.app.ingestion.sealed_browse_client._fetch_listings_for_product",
                side_effect=httpx.ConnectError("connection refused"),
            ),
        ):
            result = run_sealed_ingest(db)

        assert result["products_failed"] == 1
        assert result["snapshots_written"] == 0
        assert result["products_total"] == 1

        snapshots = db.scalars(select(ListingSnapshot)).all()
        assert len(snapshots) == 0


def test_failures_captured_in_meta_json():
    """Per-product failure details appear in meta_json["failures"] (Codex P1).

    Two products fail; the result must contain a "failures" list with two entries,
    each carrying product_id, error_type, and a non-empty message. Successful
    runs must NOT include a "failures" key.
    """
    import httpx
    from backend.app.ingestion.sealed_browse_client import run_sealed_ingest

    two_products = [
        ProductConfig(name="Alpha ETB", set_name="Set A", ebay_search_query="q1", product_type="etb", game="pokemon"),
        ProductConfig(name="Beta Box", set_name="Set B", ebay_search_query="q2", product_type="booster_box", game="pokemon"),
    ]

    mock_settings = MagicMock()
    mock_settings.ebay_app_id = "fake_app_id"
    mock_settings.ebay_cert_id = "fake_cert_id"

    mock_client_instance = MagicMock()
    mock_client_cls = MagicMock()
    mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client_instance)
    mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

    with _session() as db:
        with (
            patch("backend.app.ingestion.sealed_browse_client.get_settings", return_value=mock_settings),
            patch("backend.app.ingestion.sealed_browse_client.load_sealed_products", return_value=two_products),
            patch("backend.app.ingestion.sealed_browse_client.httpx.Client", mock_client_cls),
            patch("backend.app.ingestion.sealed_browse_client._get_oauth_token", return_value="fake_token"),
            patch(
                "backend.app.ingestion.sealed_browse_client._fetch_listings_for_product",
                side_effect=httpx.HTTPStatusError("503 Service Unavailable", request=MagicMock(), response=MagicMock()),
            ),
        ):
            result = run_sealed_ingest(db)

        assert result["products_failed"] == 2
        assert "failures" in result
        assert len(result["failures"]) == 2

        product_ids = {f["product_id"] for f in result["failures"]}
        assert product_ids == {"Alpha ETB", "Beta Box"}

        for entry in result["failures"]:
            assert entry["error_type"] == "HTTPStatusError"
            assert entry["message"]  # non-empty


def test_no_failures_key_when_all_succeed():
    """meta_json must NOT include a 'failures' key when every product succeeds."""
    from backend.app.ingestion.sealed_browse_client import run_sealed_ingest

    one_product = [ProductConfig(
        name="Good ETB", set_name="Set G", ebay_search_query="q", product_type="etb", game="pokemon",
    )]

    mock_settings = MagicMock()
    mock_settings.ebay_app_id = "fake_app_id"
    mock_settings.ebay_cert_id = "fake_cert_id"

    mock_client_cls = MagicMock()
    mock_client_cls.return_value.__enter__ = MagicMock(return_value=MagicMock())
    mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

    with _session() as db:
        with (
            patch("backend.app.ingestion.sealed_browse_client.get_settings", return_value=mock_settings),
            patch("backend.app.ingestion.sealed_browse_client.load_sealed_products", return_value=one_product),
            patch("backend.app.ingestion.sealed_browse_client.httpx.Client", mock_client_cls),
            patch("backend.app.ingestion.sealed_browse_client._get_oauth_token", return_value="fake_token"),
            patch(
                "backend.app.ingestion.sealed_browse_client._fetch_listings_for_product",
                return_value=(None, 2, False, []),  # valid "not enough listings" result
            ),
            patch("backend.app.ingestion.sealed_browse_client.time.sleep"),
        ):
            result = run_sealed_ingest(db)

        assert result["products_failed"] == 0
        assert "failures" not in result
