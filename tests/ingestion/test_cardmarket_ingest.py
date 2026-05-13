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
