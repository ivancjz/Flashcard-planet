"""eBay web-scrape ingestion for YGO sold prices.

Scrapes eBay completed-listings pages (no API key needed) to get real USD
sold prices for YGO assets. One median-price row per asset per run.

Source: 'ebay_web_sold'  —  USD-denominated, enters standard delta path.
DO NOT write ask prices or multi-card lot prices here.

Rate limit: 1 request per SCRAPE_DELAY_SECONDS to avoid bot detection.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory

logger = logging.getLogger(__name__)

EBAY_WEB_SOLD_SOURCE = "ebay_web_sold"
SCRAPE_DELAY_SECONDS = 2.0
PRICE_FLOOR_USD = Decimal("0.50")
PRICE_CEILING_USD = Decimal("500.00")

_SKIP_KEYWORDS = frozenset({
    "booster box", "booster pack", "display", "factory sealed", "sealed pack",
    "playmat", "lot of", "deck core", "collection", "bundle",
})
_MULTI_QTY_RE = re.compile(r"(?:^|\s)(\d+)x\s|\sx\s*(\d+)(?:\s|$)|playset", re.IGNORECASE)
_GRADE_RE = re.compile(r"\b(PSA|BGS|CGC|HGA)\b", re.IGNORECASE)
_SOLD_RE = re.compile(
    r"Sold\s+((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},\s+\d{4})"
    r"(.*?)"
    r"\$(\d+(?:\.\d{2})?)",
    re.DOTALL,
)
_LANG_JP_RE = re.compile(r"japanese|POTE-JP|\bJP\d|\bOCG\b", re.IGNORECASE)
_LANG_KR_RE = re.compile(r"korean|POTE-KR|\bKR\d", re.IGNORECASE)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.ebay.com/",
}


@dataclass
class EbayWebScrapeResult:
    assets_attempted: int = 0
    assets_written: int = 0
    assets_skipped_no_sales: int = 0
    assets_skipped_http_error: int = 0
    price_points_written: int = 0
    captured_at: datetime | None = None


def _build_search_url(name: str, card_number: str, rarity: str) -> str:
    """Return a completed-listings eBay search URL for one card + rarity."""
    query = f"{name} {card_number} {rarity} yugioh"
    params = urlencode({
        "_nkw": query,
        "LH_Sold": "1",
        "LH_Complete": "1",
        "_sacat": "2536",
    })
    return f"https://www.ebay.com/sch/i.html?{params}"


def _extract_sold_items(page_text: str) -> list[dict]:
    """Parse all Sold <date> ... $price blocks from eBay page text."""
    items = []
    for m in _SOLD_RE.finditer(page_text):
        date_str = m.group(1).strip()
        raw_title = m.group(2)
        price_str = m.group(3)

        title = raw_title.split("Opens in a new window")[0].strip()
        title = re.sub(r"\s*(Pre-Owned|Brand New).*", "", title, flags=re.IGNORECASE).strip()
        title = re.sub(r"\s+", " ", title).strip()

        try:
            price = Decimal(price_str)
        except InvalidOperation:
            continue

        if not title:
            continue

        items.append({"sold_date": date_str, "title": title, "price_usd": price})

    return items


def _filter_valid_singles(items: list[dict]) -> list[dict]:
    """Keep only EN ungraded single-card sold items within price bounds."""
    valid = []
    for item in items:
        title = item["title"]
        tl = title.lower()
        price = item["price_usd"]

        if price < PRICE_FLOOR_USD or price > PRICE_CEILING_USD:
            continue
        if any(kw in tl for kw in _SKIP_KEYWORDS):
            continue
        if _MULTI_QTY_RE.search(title):
            continue
        if _GRADE_RE.search(title):
            continue
        if _LANG_JP_RE.search(title) or _LANG_KR_RE.search(title):
            continue

        valid.append(item)

    return valid


def _median_price(prices: list[Decimal]) -> Decimal:
    """Return the median of a non-empty list of Decimal prices."""
    if not prices:
        raise ValueError("Cannot compute median of empty list")
    sorted_prices = sorted(prices)
    n = len(sorted_prices)
    mid = n // 2
    if n % 2 == 1:
        return sorted_prices[mid]
    return (sorted_prices[mid - 1] + sorted_prices[mid]) / 2


def _fetch_page_text(url: str, client: httpx.Client) -> str | None:
    """Fetch eBay page and return its text content. Returns None on HTTP error."""
    try:
        resp = client.get(url, headers=_HEADERS, follow_redirects=True, timeout=20.0)
        resp.raise_for_status()
        return resp.text
    except httpx.HTTPStatusError as exc:
        logger.warning("ebay_web_http_error url=%s status=%s", url, exc.response.status_code)
        return None
    except httpx.RequestError as exc:
        logger.warning("ebay_web_request_error url=%s error=%s", url, exc)
        return None


def ingest_ebay_web_sold(
    session: Session,
    *,
    asset_ids: list[uuid.UUID] | None = None,
) -> EbayWebScrapeResult:
    """Scrape eBay sold listings for YGO assets and write median prices to price_history.

    If asset_ids is given, only those assets are processed (for testing / partial runs).
    Otherwise all yugioh assets with a non-null variant (rarity) are processed.
    """
    result = EbayWebScrapeResult()
    captured_at = datetime.now(UTC).replace(microsecond=0)
    result.captured_at = captured_at

    query = select(Asset).where(
        Asset.game == "yugioh",
        Asset.variant.isnot(None),
        Asset.card_number.isnot(None),
    )
    if asset_ids:
        query = query.where(Asset.id.in_(asset_ids))

    assets = session.scalars(query).all()

    with httpx.Client() as client:
        for asset in assets:
            result.assets_attempted += 1

            url = _build_search_url(
                name=asset.name,
                card_number=asset.card_number,
                rarity=asset.variant,
            )

            page_text = _fetch_page_text(url, client)
            if page_text is None:
                result.assets_skipped_http_error += 1
                time.sleep(SCRAPE_DELAY_SECONDS)
                continue

            raw_items = _extract_sold_items(page_text)
            valid_items = _filter_valid_singles(raw_items)

            if not valid_items:
                logger.debug(
                    "ebay_web_no_sales asset=%s card=%s variant=%s raw=%s",
                    asset.name, asset.card_number, asset.variant, len(raw_items),
                )
                result.assets_skipped_no_sales += 1
                time.sleep(SCRAPE_DELAY_SECONDS)
                continue

            prices = [item["price_usd"] for item in valid_items]
            median = _median_price(prices)

            stmt = pg_insert(PriceHistory).values(
                id=uuid.uuid4(),
                asset_id=asset.id,
                source=EBAY_WEB_SOLD_SOURCE,
                currency="USD",
                price=median,
                captured_at=captured_at,
                market_segment="raw",
            ).on_conflict_do_nothing()

            rows = session.execute(stmt)
            if rows.rowcount:
                result.price_points_written += 1
                result.assets_written += 1

            logger.info(
                "ebay_web_sold_written asset=%s card=%s rarity=%s median=%.2f valid=%s raw=%s",
                asset.name, asset.card_number, asset.variant,
                float(median), len(valid_items), len(raw_items),
            )

            time.sleep(SCRAPE_DELAY_SECONDS)

    session.commit()
    logger.info(
        "ebay_web_sold_complete attempted=%s written=%s no_sales=%s http_errors=%s",
        result.assets_attempted, result.assets_written,
        result.assets_skipped_no_sales, result.assets_skipped_http_error,
    )
    return result
