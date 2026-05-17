#!/usr/bin/env python3
"""
eBay sold-listing scraper — runs in GitHub Actions (GitHub IP, not blocked by Akamai).

Fetches YGO asset list from Railway admin API, scrapes eBay completed listings,
posts results back to Railway which writes to price_history.

Usage:
  python scripts/github_ebay_scrape.py

Required env vars:
  FLASHCARD_APP_URL    e.g. https://flashcard-planet.up.railway.app
  FLASHCARD_ADMIN_KEY  X-Admin-Key value

Optional:
  DRY_RUN=1            Print results without posting to Railway
"""
from __future__ import annotations

import logging
import os
import re
import sys
import time
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

import httpx
from curl_cffi import requests as cffi_requests
from curl_cffi.requests.exceptions import HTTPError as CffiHTTPError
from curl_cffi.requests.exceptions import RequestException as CffiRequestException
from curl_cffi.requests.exceptions import Timeout as CffiTimeout

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

APP_URL = os.environ.get("FLASHCARD_APP_URL", "").rstrip("/")
ADMIN_KEY = os.environ.get("FLASHCARD_ADMIN_KEY", "")
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

SCRAPE_DELAY = 2.0
PRICE_FLOOR = Decimal("0.50")
PRICE_CEILING = Decimal("500.00")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.ebay.com/",
}

# ── Parsing (mirrors ebay_web_scrape.py — keep in sync) ───────────────────────

_SKIP_KEYWORDS = frozenset({
    "booster box", "booster pack", "display", "factory sealed", "sealed pack",
    "playmat", "lot of", "deck core", "collection", "bundle",
})
_MULTI_QTY_RE = re.compile(r"(?:^|\s)(\d+)x\s|\sx\s*(\d+)(?:\s|$)|playset", re.IGNORECASE)
_GRADE_RE = re.compile(r"\b(PSA|BGS|CGC|HGA)\b", re.IGNORECASE)
_SOLD_RE = re.compile(
    r"Sold\s+((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},\s+\d{4})"
    r"(.*?)\$(\d+(?:\.\d{2})?)",
    re.DOTALL,
)
_LANG_JP_RE = re.compile(r"japanese|POTE-JP|\bJP\d|\bOCG\b", re.IGNORECASE)
_LANG_KR_RE = re.compile(r"korean|POTE-KR|\bKR\d", re.IGNORECASE)
_FIRST_EDITION_RE = re.compile(r"\b1st\b|\bfirst\s+edition\b", re.IGNORECASE)


def _build_url(name: str, card_number: str, rarity: str) -> str:
    query = f"{name} {card_number} {rarity} 1st Edition yugioh"
    params = urlencode({"_nkw": query, "LH_Sold": "1", "LH_Complete": "1", "_sacat": "2536"})
    return f"https://www.ebay.com/sch/i.html?{params}"


def _extract_items(html: str) -> list[dict]:
    items = []
    for m in _SOLD_RE.finditer(html):
        raw_title = m.group(2)
        price_str = m.group(3)
        title = raw_title.split("Opens in a new window")[0].strip()
        title = re.sub(r"\s*(Pre-Owned|Brand New).*", "", title, flags=re.IGNORECASE).strip()
        title = re.sub(r"\s+", " ", title).strip()
        try:
            price = Decimal(price_str)
        except InvalidOperation:
            continue
        if title:
            items.append({"title": title, "price_usd": price})
    return items


def _filter_singles(items: list[dict], rarity: str = "") -> list[dict]:
    rarity_lower = rarity.lower()
    valid = []
    for item in items:
        title = item["title"]
        tl = title.lower()
        price = item["price_usd"]
        if price < PRICE_FLOOR or price > PRICE_CEILING:
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
            continue
        if rarity_lower and rarity_lower not in tl:
            continue
        valid.append(item)
    return valid


def _median(prices: list[Decimal]) -> Decimal:
    s = sorted(prices)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 == 1 else (s[mid - 1] + s[mid]) / 2


# ── HTTP ──────────────────────────────────────────────────────────────────────

def _fetch(session: cffi_requests.Session, url: str) -> tuple[str | None, str | None]:
    """Returns (html, error_key). Uses curl_cffi Chrome fingerprint."""
    try:
        resp = session.get(url, headers=_HEADERS, allow_redirects=True, timeout=20)
        if resp.status_code != 200:
            log.warning("HTTP %s", resp.status_code)
            return None, str(resp.status_code)
        return resp.text, None
    except CffiHTTPError as exc:
        status = getattr(getattr(exc, "response", None), "status_code", "http_error")
        log.warning("HTTP error: %s", status)
        return None, str(status)
    except CffiTimeout:
        return None, "timeout"
    except CffiRequestException as exc:
        log.warning("request error: %s", exc)
        return None, "connection_error"


# ── Railway API ───────────────────────────────────────────────────────────────

def _admin_headers() -> dict:
    return {"X-Admin-Key": ADMIN_KEY}


MAX_ASSETS = int(os.environ.get("EBAY_MAX_ASSETS", "250"))


def fetch_assets() -> list[dict]:
    """Fetch YGO asset list from Railway, capped at MAX_ASSETS."""
    resp = httpx.get(
        f"{APP_URL}/admin/diag/ygo-scrape-targets",
        headers=_admin_headers(),
        params={"max_assets": MAX_ASSETS},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["assets"]


def post_results(prices: list[dict], meta: dict, run_date: str) -> dict:
    if DRY_RUN:
        log.info("[DRY RUN] would post %d prices: %s", len(prices), meta)
        return {"status": "dry_run", "written": 0}
    resp = httpx.post(
        f"{APP_URL}/admin/trigger/ebay-sold-write",
        headers={**_admin_headers(), "Content-Type": "application/json"},
        json={"prices": prices, "meta": meta, "run_date": run_date},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def post_failure(meta: dict, error: str, run_date: str) -> None:
    """POST a failure record so Railway's scheduler_run_log always has an entry."""
    if DRY_RUN:
        return
    try:
        httpx.post(
            f"{APP_URL}/admin/trigger/ebay-sold-write",
            headers={**_admin_headers(), "Content-Type": "application/json"},
            json={
                "prices": [],
                "meta": {**meta, "error": error, "runner": "github_actions"},
                "run_date": run_date,
            },
            timeout=15,
        )
    except Exception as exc:
        log.warning("Failed to post failure record to Railway: %s", exc)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    import datetime as _dt
    run_date = _dt.date.today().isoformat()  # YYYY-MM-DD — idempotency key

    if not APP_URL or not ADMIN_KEY:
        log.error("FLASHCARD_APP_URL and FLASHCARD_ADMIN_KEY must be set")
        return 1

    prices: list[dict] = []
    http_error_counts: dict[str, int] = {}
    skipped_no_sales = 0
    skipped_http = 0
    assets: list[dict] = []

    try:
        assets = fetch_assets()
        log.info("Fetched %d YGO assets to scrape (max=%d)", len(assets), MAX_ASSETS)

        with cffi_requests.Session(impersonate="chrome136") as session:
            for asset in assets:
                url = _build_url(asset["name"], asset["card_number"], asset["variant"])
                html, err_key = _fetch(session, url)

                if html is None:
                    skipped_http += 1
                    http_error_counts[err_key] = http_error_counts.get(err_key, 0) + 1
                    time.sleep(SCRAPE_DELAY)
                    continue

                raw = _extract_items(html)
                valid = _filter_singles(raw, rarity=asset.get("variant", ""))

                if valid:
                    median = _median([i["price_usd"] for i in valid])
                    prices.append({"asset_id": asset["id"], "price_usd": str(median)})
                    log.info("  %s → $%s (%d sales)", asset["card_number"], median, len(valid))
                else:
                    skipped_no_sales += 1
                    log.debug("  %s: no valid sales (raw=%d)", asset["card_number"], len(raw))

                time.sleep(SCRAPE_DELAY)

    except Exception as exc:
        log.exception("Scraper failed: %s", exc)
        # Always write a run record so Railway heartbeat monitoring sees this run
        post_failure(
            meta={
                "assets_attempted": len(assets),
                "assets_written": 0,
                "assets_skipped_no_sales": skipped_no_sales,
                "assets_skipped_http_error": skipped_http,
                "http_error_counts": http_error_counts,
            },
            error=str(exc),
            run_date=run_date,
        )
        return 1

    meta = {
        "assets_attempted": len(assets),
        "assets_written": len(prices),
        "assets_skipped_no_sales": skipped_no_sales,
        "assets_skipped_http_error": skipped_http,
        "http_error_counts": http_error_counts,
        "runner": "github_actions",
    }
    log.info("Scrape complete: %s", meta)

    result = post_results(prices, meta, run_date)
    log.info("Railway response: %s", result)

    if skipped_http == len(assets) and len(assets) > 0:
        log.error("All assets returned HTTP errors — possible IP block on GitHub Actions")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
