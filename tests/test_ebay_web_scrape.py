"""Unit tests for eBay web-scrape ingestion parser and filter logic.

No HTTP calls, no DB. Tests only the pure functions that parse and filter
sold-listing text extracted from eBay search results pages.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.app.ingestion.ebay_web_scrape import (
    EbayWebScrapeResult,
    _build_search_url,
    _extract_sold_items,
    _filter_valid_singles,
    _median_price,
)


# ── _build_search_url ─────────────────────────────────────────────────────────

def test_build_search_url_encodes_spaces():
    url = _build_search_url("Spright Elf", "POTE-EN049", "Ultra Rare")
    assert "Spright+Elf" in url or "Spright%20Elf" in url
    assert "POTE-EN049" in url
    assert "Ultra+Rare" in url or "Ultra%20Rare" in url
    assert "LH_Sold=1" in url
    assert "LH_Complete=1" in url
    assert "_sacat=2536" in url


def test_build_search_url_includes_yugioh():
    url = _build_search_url("Exosister Martha", "POTE-EN025", "Secret Rare")
    assert "yugioh" in url.lower()


# ── _extract_sold_items ───────────────────────────────────────────────────────

SAMPLE_PAGE_TEXT = """
Skip to main contentHi! Sign in
Sold  May 15, 2026Yugioh Spright Elf POTE-EN049 Ultra Rare 1st Edition Near MintOpens in a new window or tab
Pre-Owned$14.99Buy It Now+$10.25 delivery

Sold  May 14, 2026yugioh TCG Spright Elf [1st Edition] POTE-EN049Opens in a new window or tab
Pre-Owned$10.90Buy It Now

Sold  May 13, 2026Spright Elf POTE-EN049 Ultra Rare Japanese OCGOpens in a new window or tab
Pre-Owned$3.33Buy It Now

Sold  May 12, 2026Yugioh Spright Elf POTE-EN049 x3 Playset Ultra RareOpens in a new window or tab
Pre-Owned$4.50Buy It Now

Sold  May 11, 2026PSA 9 Spright Elf POTE-EN049 Ultra Rare 1st EdOpens in a new window or tab
Pre-Owned$45.00Buy It Now

Sold  May 10, 2026Spright Elf POTE-EN049 Ultra Rare 1st Edition LPOpens in a new window or tab
Pre-Owned$6.50Buy It Now

Sold  May 9, 2026Spright Elf Booster Box POTE 24-pack sealedOpens in a new window or tab
Brand New$37.95Buy It Now
"""


def test_extract_sold_items_returns_all_raw():
    items = _extract_sold_items(SAMPLE_PAGE_TEXT)
    assert len(items) == 7


def test_extract_sold_items_date_and_price():
    items = _extract_sold_items(SAMPLE_PAGE_TEXT)
    first = items[0]
    assert first["sold_date"] == "May 15, 2026"
    assert first["price_usd"] == Decimal("14.99")
    assert "Spright Elf" in first["title"]


# ── _filter_valid_singles ─────────────────────────────────────────────────────

def test_filter_drops_japanese():
    items = _extract_sold_items(SAMPLE_PAGE_TEXT)
    valid = _filter_valid_singles(items)
    titles = [i["title"] for i in valid]
    assert not any("Japanese" in t or "OCG" in t for t in titles)


def test_filter_drops_multi_quantity():
    items = _extract_sold_items(SAMPLE_PAGE_TEXT)
    valid = _filter_valid_singles(items)
    titles = [i["title"] for i in valid]
    assert not any("x3" in t or "Playset" in t for t in titles)


def test_filter_drops_graded():
    items = _extract_sold_items(SAMPLE_PAGE_TEXT)
    valid = _filter_valid_singles(items)
    titles = [i["title"] for i in valid]
    assert not any("PSA" in t or "BGS" in t or "CGC" in t for t in titles)


def test_filter_drops_sealed():
    items = _extract_sold_items(SAMPLE_PAGE_TEXT)
    valid = _filter_valid_singles(items)
    titles = [i["title"] for i in valid]
    assert not any("Booster Box" in t for t in titles)


def test_filter_keeps_en_singles():
    items = _extract_sold_items(SAMPLE_PAGE_TEXT)
    valid = _filter_valid_singles(items)
    prices = sorted(i["price_usd"] for i in valid)
    assert Decimal("6.50") in prices
    assert Decimal("10.90") in prices
    assert Decimal("14.99") in prices


def test_filter_drops_prices_below_floor():
    text = """
Sold  May 15, 2026Spright Elf POTE-EN049 Ultra RareOpens in a new window or tab
Pre-Owned$0.25Buy It Now
"""
    items = _extract_sold_items(text)
    valid = _filter_valid_singles(items)
    assert len(valid) == 0


def test_filter_drops_prices_above_ceiling():
    text = """
Sold  May 15, 2026Spright Elf POTE-EN049 Ultra Rare 1st EdOpens in a new window or tab
Pre-Owned$750.00Buy It Now
"""
    items = _extract_sold_items(text)
    valid = _filter_valid_singles(items)
    assert len(valid) == 0


# ── _median_price ─────────────────────────────────────────────────────────────

def test_median_odd_count():
    prices = [Decimal("5"), Decimal("10"), Decimal("15")]
    assert _median_price(prices) == Decimal("10")


def test_median_even_count():
    prices = [Decimal("5"), Decimal("10"), Decimal("15"), Decimal("20")]
    assert _median_price(prices) == Decimal("12.50")


def test_median_single():
    assert _median_price([Decimal("7.99")]) == Decimal("7.99")


def test_median_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        _median_price([])


# ── EbayWebScrapeResult ───────────────────────────────────────────────────────

def test_result_dataclass_defaults():
    r = EbayWebScrapeResult()
    assert r.assets_attempted == 0
    assert r.assets_written == 0
    assert r.assets_skipped_no_sales == 0
    assert r.assets_skipped_http_error == 0
    assert r.price_points_written == 0


# ── Rarity title-confirmation filter (Mode 2 fix) ─────────────────────────────

_RARITY_FILTER_TEXT = """
Sold  May 17, 2026Kurikara Divincarnate POTE-EN031 Secret Rare 1st Edition NMOpens in a new window or tab
Pre-Owned$14.00Buy It Now

Sold  May 17, 2026Kurikara Divincarnate POTE-EN031 Starlight Rare 1st Edition NMOpens in a new window or tab
Pre-Owned$250.00Buy It Now

Sold  May 17, 2026Kurikara Divincarnate POTE-EN031 Collector's Rare 1st Edition NMOpens in a new window or tab
Pre-Owned$180.00Buy It Now

Sold  May 17, 2026Kurikara Divincarnate POTE-EN031 secret rare unlimited editionOpens in a new window or tab
Pre-Owned$8.50Buy It Now
"""


def test_rarity_confirmation_drops_listings_missing_queried_rarity():
    items = _extract_sold_items(_RARITY_FILTER_TEXT)
    valid = _filter_valid_singles(items, rarity="Secret Rare")
    prices = [i["price_usd"] for i in valid]
    # Starlight Rare ($250) and Collector's Rare ($180) titles do not contain
    # "Secret Rare" — they must be dropped as bleed-through variants
    assert Decimal("250.00") not in prices
    assert Decimal("180.00") not in prices


def test_rarity_confirmation_keeps_matching_listings():
    items = _extract_sold_items(_RARITY_FILTER_TEXT)
    valid = _filter_valid_singles(items, rarity="Secret Rare")
    prices = [i["price_usd"] for i in valid]
    # Both Secret Rare listings ($14.00 and $8.50) must be kept
    assert Decimal("14.00") in prices
    assert Decimal("8.50") in prices


def test_rarity_confirmation_is_case_insensitive():
    items = _extract_sold_items(_RARITY_FILTER_TEXT)
    # queried rarity in lower case must still match title with title-case
    valid_lower = _filter_valid_singles(items, rarity="secret rare")
    valid_title = _filter_valid_singles(items, rarity="Secret Rare")
    assert len(valid_lower) == len(valid_title)


def test_rarity_confirmation_allows_substring_match():
    text = """
Sold  May 17, 2026Exosister Martha POTE-EN025 Secret Rare 1st Edition Near Mint YugiohOpens in a new window or tab
Pre-Owned$9.99Buy It Now
"""
    items = _extract_sold_items(text)
    valid = _filter_valid_singles(items, rarity="Secret Rare")
    # Title contains "Secret Rare" as a substring — must be kept
    assert len(valid) == 1
    assert valid[0]["price_usd"] == Decimal("9.99")


# ── Query format — 1st Edition scope (Mode 1 workaround) ─────────────────────

def test_built_query_contains_first_edition():
    url = _build_search_url("Spright Elf", "POTE-EN049", "Ultra Rare")
    assert "1st+Edition" in url or "1st%20Edition" in url or "1st+edition" in url


def test_built_query_retains_existing_elements():
    url = _build_search_url("Exosister Martha", "POTE-EN025", "Secret Rare")
    assert "Exosister" in url
    assert "POTE-EN025" in url
    assert "Secret" in url
    assert "yugioh" in url.lower()
    assert "LH_Sold=1" in url
