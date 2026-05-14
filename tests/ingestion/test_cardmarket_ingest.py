# tests/ingestion/test_cardmarket_ingest.py
from __future__ import annotations
import json
import pytest
from unittest.mock import patch, MagicMock
from backend.app.ingestion.game_data.cardmarket_catalog import (
    CardmarketCatalog,
    CM_PRICE_GUIDE_URL,
    CM_SINGLES_CATALOG_URL,
    GAME_ID_YGO,
)

FAKE_CATALOG = {
    "version": 1,
    "createdAt": "2026-05-13T02:43:22+0200",
    "products": [
        {"idProduct": 101788, "name": "Ash Blossom & Joyous Spring", "idCategory": 5,
         "categoryName": "Yugioh Single", "idExpansion": 1011, "idMetacard": 101779,
         "dateAdded": "2020-01-01 00:00:00"},
        {"idProduct": 102000, "name": "Dark Magician", "idCategory": 5,
         "categoryName": "Yugioh Single", "idExpansion": 1064, "idMetacard": 100001,
         "dateAdded": "2007-01-01 00:00:00"},
        {"idProduct": 102001, "name": "Dark Magician", "idCategory": 5,
         "categoryName": "Yugioh Single", "idExpansion": 1077, "idMetacard": 100001,
         "dateAdded": "2007-01-01 00:00:00"},
    ]
}

FAKE_PRICE_GUIDE = {
    "version": 1,
    "createdAt": "2026-05-13T02:43:22+0200",
    "priceGuides": [
        {"idProduct": 101788, "idCategory": 5, "avg": 5.0, "low": 2.0, "trend": 4.8,
         "avg1": 6.0, "avg7": 5.0, "avg30": 4.5, "avg-foil": None, "low-foil": None,
         "trend-foil": None, "avg1-foil": None, "avg7-foil": None, "avg30-foil": None},
        {"idProduct": 102000, "idCategory": 5, "avg": 50.0, "low": 40.0, "trend": 48.0,
         "avg1": None, "avg7": 50.0, "avg30": 45.0, "avg-foil": None, "low-foil": None,
         "trend-foil": None, "avg1-foil": None, "avg7-foil": None, "avg30-foil": None},
        {"idProduct": 102001, "idCategory": 5, "avg": None, "low": None, "trend": None,
         "avg1": None, "avg7": None, "avg30": None, "avg-foil": None, "low-foil": None,
         "trend-foil": None, "avg1-foil": None, "avg7-foil": None, "avg30-foil": None},
    ]
}


def _mock_httpx(catalog_data, price_data):
    def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.status_code = 200
        resp.headers = {}
        if "productList" in url:
            resp.json.return_value = catalog_data
        else:
            resp.json.return_value = price_data
        return resp
    return fake_get


def test_catalog_name_lookup_finds_card():
    with patch("httpx.get", side_effect=_mock_httpx(FAKE_CATALOG, FAKE_PRICE_GUIDE)):
        cat = CardmarketCatalog.download(game_id=GAME_ID_YGO)
    ids = cat.product_ids_for_name("Ash Blossom & Joyous Spring")
    assert ids == [101788]


def test_catalog_name_lookup_returns_all_printings():
    with patch("httpx.get", side_effect=_mock_httpx(FAKE_CATALOG, FAKE_PRICE_GUIDE)):
        cat = CardmarketCatalog.download(game_id=GAME_ID_YGO)
    ids = cat.product_ids_for_name("Dark Magician")
    assert set(ids) == {102000, 102001}


def test_catalog_price_for_product_returns_avg7():
    with patch("httpx.get", side_effect=_mock_httpx(FAKE_CATALOG, FAKE_PRICE_GUIDE)):
        cat = CardmarketCatalog.download(game_id=GAME_ID_YGO)
    prices = cat.prices_for_product(101788)
    assert prices["avg7"] == 5.0
    assert prices["avg30"] == 4.5
    assert prices["avg1"] == 6.0


def test_catalog_price_returns_none_for_all_null():
    with patch("httpx.get", side_effect=_mock_httpx(FAKE_CATALOG, FAKE_PRICE_GUIDE)):
        cat = CardmarketCatalog.download(game_id=GAME_ID_YGO)
    prices = cat.prices_for_product(102001)
    assert prices["avg7"] is None
    assert prices["avg30"] is None


def test_catalog_price_avg7_none_when_absent():
    with patch("httpx.get", side_effect=_mock_httpx(FAKE_CATALOG, FAKE_PRICE_GUIDE)):
        cat = CardmarketCatalog.download(game_id=GAME_ID_YGO)
    prices = cat.prices_for_product(102000)
    assert prices["avg7"] == 50.0
    assert prices["avg1"] is None


def test_catalog_stores_etag_from_response():
    def fake_get_with_etag(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.status_code = 200
        resp.headers = {"ETag": '"abc123"'}
        if "productList" in url:
            resp.json.return_value = FAKE_CATALOG
        else:
            resp.json.return_value = FAKE_PRICE_GUIDE
        return resp

    with patch("httpx.get", side_effect=fake_get_with_etag):
        cat = CardmarketCatalog.download(game_id=GAME_ID_YGO)
    assert cat.etag == '"abc123"'


def test_catalog_returns_none_on_304():
    """When S3 returns 304, download() returns None — ingest should skip."""
    def fake_get_304(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 304
        resp.headers = {}
        resp.raise_for_status = MagicMock()
        return resp

    with patch("httpx.get", side_effect=fake_get_304):
        result = CardmarketCatalog.download(game_id=GAME_ID_YGO, etag='"abc123"')
    assert result is None

# ── Task 2: ingest function tests ─────────────────────────────────────────────

from contextlib import contextmanager
from datetime import UTC, datetime
import uuid

from sqlalchemy import JSON, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
from backend.app.db.base import Base
from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory
from backend.app.ingestion.cardmarket import ingest_cardmarket_ygo, CardmarketIngestionResult


def _coerce_postgres_types():
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()


@contextmanager
def _db():
    _coerce_postgres_types()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as db:
        yield db
    Base.metadata.drop_all(engine)


def _make_asset(session, name: str, game: str = "yugioh") -> Asset:
    asset = Asset(
        id=uuid.uuid4(),
        asset_class="TCG",
        game=game,
        name=name,
        set_name="POTE",
        card_number="001",
        language="EN",
        variant="Super Rare",
    )
    session.add(asset)
    session.flush()
    return asset


def _make_catalog_with(
    card_name: str,
    product_id: int,
    avg7: float | None,
    avg30: float | None,
    avg1: float | None = None,
) -> CardmarketCatalog:
    catalog = CardmarketCatalog(game_id=GAME_ID_YGO, created_at="2026-05-13T02:43:22+0200")
    catalog._name_to_ids[card_name.lower()] = [product_id]
    catalog._prices[product_id] = {"avg1": avg1, "avg7": avg7, "avg30": avg30}
    return catalog


def test_ingest_writes_avg7_and_avg30_rows():
    with _db() as db:
        asset = _make_asset(db, "Ash Blossom & Joyous Spring")
        catalog = _make_catalog_with("Ash Blossom & Joyous Spring", 101788, avg7=5.0, avg30=4.5)
        result = ingest_cardmarket_ygo(db, catalog=catalog)
        db.commit()

        rows = db.execute(select(PriceHistory).where(PriceHistory.asset_id == asset.id)).scalars().all()
        sources = {r.source for r in rows}
        assert "cardmarket_avg7" in sources
        assert "cardmarket_avg30" in sources
        assert result.price_points_written == 2


def test_ingest_writes_avg1_when_present():
    with _db() as db:
        asset = _make_asset(db, "Ash Blossom & Joyous Spring")
        catalog = _make_catalog_with("Ash Blossom & Joyous Spring", 101788, avg7=5.0, avg30=4.5, avg1=6.0)
        result = ingest_cardmarket_ygo(db, catalog=catalog)
        db.commit()

        rows = db.execute(select(PriceHistory).where(PriceHistory.asset_id == asset.id)).scalars().all()
        sources = {r.source for r in rows}
        assert "cardmarket_avg1" in sources
        assert result.price_points_written == 3


def test_ingest_skips_avg1_when_null():
    with _db() as db:
        asset = _make_asset(db, "Ash Blossom & Joyous Spring")
        catalog = _make_catalog_with("Ash Blossom & Joyous Spring", 101788, avg7=5.0, avg30=4.5, avg1=None)
        ingest_cardmarket_ygo(db, catalog=catalog)
        db.commit()

        rows = db.execute(select(PriceHistory).where(PriceHistory.asset_id == asset.id)).scalars().all()
        sources = {r.source for r in rows}
        assert "cardmarket_avg1" not in sources


def test_ingest_skips_card_with_null_avg7_and_avg30():
    with _db() as db:
        asset = _make_asset(db, "Dark Magician")
        catalog = _make_catalog_with("Dark Magician", 102000, avg7=None, avg30=None)
        result = ingest_cardmarket_ygo(db, catalog=catalog)
        db.commit()

        rows = db.execute(select(PriceHistory).where(PriceHistory.asset_id == asset.id)).scalars().all()
        assert len(rows) == 0
        assert result.assets_skipped_no_price == 1


def test_ingest_sets_market_segment_raw():
    with _db() as db:
        asset = _make_asset(db, "Ash Blossom & Joyous Spring")
        catalog = _make_catalog_with("Ash Blossom & Joyous Spring", 101788, avg7=5.0, avg30=4.5)
        ingest_cardmarket_ygo(db, catalog=catalog)
        db.commit()

        rows = db.execute(select(PriceHistory).where(PriceHistory.asset_id == asset.id)).scalars().all()
        for row in rows:
            assert row.market_segment == "raw", f"Expected market_segment='raw', got {row.market_segment!r}"


def test_ingest_sets_currency_eur():
    with _db() as db:
        asset = _make_asset(db, "Ash Blossom & Joyous Spring")
        catalog = _make_catalog_with("Ash Blossom & Joyous Spring", 101788, avg7=5.0, avg30=4.5)
        ingest_cardmarket_ygo(db, catalog=catalog)
        db.commit()

        rows = db.execute(select(PriceHistory).where(PriceHistory.asset_id == asset.id)).scalars().all()
        for row in rows:
            assert row.currency == "EUR"


def test_ingest_caches_cm_product_id_in_metadata():
    with _db() as db:
        asset = _make_asset(db, "Ash Blossom & Joyous Spring")
        catalog = _make_catalog_with("Ash Blossom & Joyous Spring", 101788, avg7=5.0, avg30=4.5)
        ingest_cardmarket_ygo(db, catalog=catalog)
        db.commit()
        db.refresh(asset)

        cached = (asset.metadata_json or {}).get("cm_product_ids", [])
        assert 101788 in cached


def test_ingest_skips_non_ygo_assets():
    with _db() as db:
        pokemon_asset = _make_asset(db, "Ash Blossom & Joyous Spring", game="pokemon")
        catalog = _make_catalog_with("Ash Blossom & Joyous Spring", 101788, avg7=5.0, avg30=4.5)
        result = ingest_cardmarket_ygo(db, catalog=catalog)
        db.commit()

        rows = db.execute(select(PriceHistory).where(PriceHistory.asset_id == pokemon_asset.id)).scalars().all()
        assert len(rows) == 0
        assert result.assets_matched == 0
