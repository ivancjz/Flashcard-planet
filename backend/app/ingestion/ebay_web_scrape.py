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
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from curl_cffi import requests as cffi_requests
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
# 1st-Edition positive filter: only keep listings that carry an explicit 1st-edition
# marker in the title. Drops Unlimited prints AND edition-ambiguous listings (no
# marker at all). Enforces 1st-Edition-only scope per ADR-001. Remove / replace
# with per-edition routing when TASK-802 ships.
_FIRST_EDITION_RE = re.compile(r"\b1st\b|\bfirst\s+edition\b", re.IGNORECASE)

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
    http_error_counts: dict[str, int] = None  # e.g. {"403": 20, "timeout": 3}

    def __post_init__(self):
        if self.http_error_counts is None:
            self.http_error_counts = {}


def _build_search_url(name: str, card_number: str, rarity: str) -> str:
    # Edition scope — WORKAROUND, see ADR-001 §Update 2026-05-17 and TASK-802.
    # ebay_web_sold currently scrapes 1st Edition only. Unlimited prints are
    # excluded by query. This is a deliberate scope limitation pending the
    # edition-aware asset model (Phase 2). DO NOT remove "1st Edition" from the
    # query until TASK-802 schema migration is complete and the scraper is
    # refactored to scrape both editions into separate asset rows.
    query = f"{name} {card_number} {rarity} 1st Edition yugioh"
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


def _filter_valid_singles(items: list[dict], *, rarity: str = "") -> list[dict]:
    """Keep only EN ungraded single-card sold items within price bounds.

    Pass rarity (the same string used in the search query, e.g. "Secret Rare")
    to enable title-level rarity confirmation. Listings whose title does not
    contain the queried rarity term are dropped, catching bleed-through from
    variant prints (Starlight Rare, Quarter-Century, Collector's Rare, etc.).
    When rarity is empty the confirmation step is skipped (backward-compatible).

    Edition: only listings with an explicit "1st" / "first edition" marker in
    the title are kept. This drops Unlimited prints AND edition-ambiguous
    listings (no edition mentioned). Remove when TASK-802 ships.
    """
    rarity_lower = rarity.lower()
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
        if not _FIRST_EDITION_RE.search(title):
            continue  # no 1st-edition marker — Unlimited or ambiguous; per ADR-001 / TASK-802
        if rarity_lower and rarity_lower not in tl:
            continue  # rarity mismatch — variant bleed-through (Starlight, QC, etc.)

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


def _fetch_page_text(url: str, client: cffi_requests.Session) -> tuple[str | None, str | None]:
    """Fetch eBay page. Returns (page_text, error_key) where error_key is None on success.

    Uses curl_cffi with impersonate="chrome136" so the TLS handshake matches a real
    Chrome browser — bypasses Akamai Bot Manager 503 blocks that httpx triggered.

    error_key is a short string for meta_json aggregation: "403", "503", "timeout",
    "connection_error", etc.
    """
    try:
        resp = client.get(url, headers=_HEADERS, allow_redirects=True, timeout=20)
        resp.raise_for_status()
        return resp.text, None
    except cffi_requests.HTTPError as exc:
        status = exc.response.status_code
        logger.warning("ebay_web_http_error url=%s status=%s", url, status)
        return None, str(status)
    except cffi_requests.Timeout as exc:
        logger.warning("ebay_web_timeout url=%s error=%s", url, exc)
        return None, "timeout"
    except cffi_requests.RequestException as exc:
        logger.warning("ebay_web_request_error url=%s error=%s", url, exc)
        return None, "connection_error"


def ingest_ebay_web_sold(
    session: Session,
    *,
    asset_ids: list[uuid.UUID] | None = None,
    max_assets: int = 250,
) -> EbayWebScrapeResult:
    """Scrape eBay sold listings for YGO assets and write median prices to price_history.

    If asset_ids is given, only those assets are processed (for testing / partial runs).
    Otherwise all yugioh assets with a non-null variant (rarity) are processed, up to
    max_assets per run (guards against unbounded external requests as the asset set grows).
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
    else:
        query = query.limit(max_assets)

    assets = session.scalars(query).all()

    with cffi_requests.Session(impersonate="chrome136") as client:
        for asset in assets:
            result.assets_attempted += 1

            url = _build_search_url(
                name=asset.name,
                card_number=asset.card_number,
                rarity=asset.variant,
            )

            page_text, err_key = _fetch_page_text(url, client)
            if page_text is None:
                result.assets_skipped_http_error += 1
                if err_key:
                    result.http_error_counts[err_key] = result.http_error_counts.get(err_key, 0) + 1
                time.sleep(SCRAPE_DELAY_SECONDS)
                continue

            raw_items = _extract_sold_items(page_text)
            valid_items = _filter_valid_singles(raw_items, rarity=asset.variant or "")

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
