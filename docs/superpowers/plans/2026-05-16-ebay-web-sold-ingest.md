# eBay Web Sold Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a daily eBay web-scrape ingestion job that writes real USD sold prices for YGO cards to `price_history` using per-rarity search queries, feeding the signal engine.

**Architecture:** `httpx` scrapes eBay completed-listings pages for each YGO asset using `"{name} {card_number} {variant} yugioh"` queries; the scraper computes a per-asset median price from EN ungraded singles and writes one `price_history` row per asset per run (source `ebay_web_sold`). No DB migration is needed — `Asset.variant` already stores YGO rarity (e.g., "Ultra Rare", "Secret Rare"). The scheduler runs the job once per 24 h behind a Category-β `Field(default=False)` kill switch.

**Tech Stack:** Python 3.13, httpx, SQLAlchemy 2, APScheduler (interval trigger), regex parsing, `price_history` table, existing `start_run`/`finish_run` scheduler pattern.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| **Create** | `backend/app/ingestion/ebay_web_scrape.py` | HTTP fetch + HTML parse + median price computation |
| **Modify** | `backend/app/services/scheduler_run_log_service.py` | Add `JOB_EBAY_WEB_SOLD` constant |
| **Modify** | `backend/app/core/config.py` | Add `ebay_web_sold_enabled: bool = Field(default=False)` kill switch |
| **Modify** | `backend/app/backstage/scheduler.py` | Add `_run_ebay_web_sold()` function + job registration + heartbeat monitoring |
| **Create** | `tests/test_ebay_web_scrape.py` | Unit tests for parser, filter, and median logic |

---

## Task 1: Add job name constant

**Files:**
- Modify: `backend/app/services/scheduler_run_log_service.py`

- [ ] **Step 1: Add the constant**

Open `backend/app/services/scheduler_run_log_service.py`. After the existing `JOB_CARDMARKET` line (currently line 34), add:

```python
JOB_EBAY_WEB_SOLD      = "ebay-web-sold"
```

- [ ] **Step 2: Verify it imports cleanly**

```bash
cd C:\Flashcard-planet
python -c "from backend.app.services.scheduler_run_log_service import JOB_EBAY_WEB_SOLD; print(JOB_EBAY_WEB_SOLD)"
```

Expected output: `ebay-web-sold`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/scheduler_run_log_service.py
git commit -m "feat(ebay-web-sold): add JOB_EBAY_WEB_SOLD constant"
```

---

## Task 2: Add kill switch to config

**Files:**
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: Add the setting**

In `backend/app/core/config.py`, find the `ebay_scheduled_ingest_enabled` line (currently line 71). Add the new setting on the next line:

```python
ebay_scheduled_ingest_enabled: bool = False
# Category β — opt-in via env var: calls external eBay web pages, no auth wall,
# but uses network bandwidth per YGO asset per run.
ebay_web_sold_enabled: bool = Field(default=False)
```

- [ ] **Step 2: Verify it loads**

```bash
python -c "from backend.app.core.config import get_settings; s=get_settings(); print(s.ebay_web_sold_enabled)"
```

Expected output: `False`

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/config.py
git commit -m "feat(ebay-web-sold): add ebay_web_sold_enabled kill switch (Category β, default False)"
```

---

## Task 3: Write the ingestion module with tests first

**Files:**
- Create: `tests/test_ebay_web_scrape.py`
- Create: `backend/app/ingestion/ebay_web_scrape.py`

### 3a — Write failing tests

- [ ] **Step 1: Write the test file**

Create `tests/test_ebay_web_scrape.py`:

```python
"""Unit tests for eBay web-scrape ingestion parser and filter logic.

No HTTP calls, no DB. Tests only the pure functions that parse and filter
sold-listing text extracted from eBay search results pages.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
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
    assert "_sacat=2536" in url  # Trading Cards category


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
    # Should find all 7 Sold entries
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
    # Should keep: May 15 ($14.99), May 14 ($10.90), May 10 ($6.50)
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
```

- [ ] **Step 2: Run tests to confirm they all fail (module not yet created)**

```bash
cd C:\Flashcard-planet
python -m pytest tests/test_ebay_web_scrape.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError` or `ImportError` — the module doesn't exist yet.

### 3b — Implement the module

- [ ] **Step 3: Create `backend/app/ingestion/ebay_web_scrape.py`**

```python
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
import statistics
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
        "_sacat": "2536",  # Collectible Card Games
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

        # Price bounds
        if price < PRICE_FLOOR_USD or price > PRICE_CEILING_USD:
            continue

        # Skip sealed product and lots
        if any(kw in tl for kw in _SKIP_KEYWORDS):
            continue

        # Skip multi-quantity
        if _MULTI_QTY_RE.search(title):
            continue

        # Skip graded
        if _GRADE_RE.search(title):
            continue

        # English only
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
                "ebay_web_sold_written asset=%s card=%s rarity=%s "
                "median=%.2f valid_sales=%s raw_sales=%s",
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
```

- [ ] **Step 4: Run tests — all should pass**

```bash
python -m pytest tests/test_ebay_web_scrape.py -v
```

Expected: all 16 tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/ebay_web_scrape.py tests/test_ebay_web_scrape.py
git commit -m "feat(ebay-web-sold): scrape parser, filter, median — TDD (16 tests green)"
```

---

## Task 4: Wire into scheduler

**Files:**
- Modify: `backend/app/backstage/scheduler.py`

- [ ] **Step 1: Import the new job constant at the top of scheduler.py**

In `backend/app/backstage/scheduler.py`, find the import block from `scheduler_run_log_service`. Add `JOB_EBAY_WEB_SOLD` to it:

```python
from backend.app.services.scheduler_run_log_service import (
    JOB_BULK_REFRESH,
    JOB_CARDMARKET,
    JOB_DIGEST,
    JOB_EBAY,
    JOB_EBAY_WEB_SOLD,          # ← add this
    JOB_HEARTBEAT,
    JOB_HISTORY_PRUNE,
    JOB_INGESTION,
    JOB_RETRY,
    JOB_SIGNALS,
    JOB_TRIAL_EXPIRY,
    JOB_YGO,
    JOB_EXPLANATION,
    JOB_BACKUP_FRESHNESS,
    JOB_SEALED_INGEST,
)
```

- [ ] **Step 2: Add startup delay**

In `_STARTUP_DELAY`, add an entry for `"ebay-web-sold"` after `"sealed-ingest"`:

```python
"sealed-ingest":          840,   # 14 min
"ebay-web-sold":          870,   # 14.5 min — after sealed-ingest; eBay scrape, 24h interval
```

- [ ] **Step 3: Add the job runner function**

Find `_run_cardmarket_ingestion` and add the following function immediately after it (before the `prepare_scheduler_for_startup` function):

```python
def _run_ebay_web_sold() -> None:
    from backend.app.ingestion.ebay_web_scrape import ingest_ebay_web_sold

    settings = get_settings()
    if not settings.ebay_web_sold_enabled:
        logger.info("ebay_web_sold_skipped reason=kill_switch")
        return

    try:
        with SessionLocal() as _log_session:
            _run_id = start_run(_log_session, JOB_EBAY_WEB_SOLD)
    except Exception as exc:
        logger.exception("start_run_failed job=%s", JOB_EBAY_WEB_SOLD)
        send_discord_alert("error", f"CRITICAL: start_run 失败 — {JOB_EBAY_WEB_SOLD}", f"error={exc}")
        return

    try:
        with SessionLocal() as session:
            result = ingest_ebay_web_sold(session)

        status = "success" if result.assets_skipped_http_error == 0 else "partial"
        with SessionLocal() as _log_session:
            finish_run(
                _log_session,
                _run_id,
                status=status,
                records_written=result.price_points_written,
                errors=result.assets_skipped_http_error,
                meta_json={
                    "assets_attempted": result.assets_attempted,
                    "assets_written": result.assets_written,
                    "assets_skipped_no_sales": result.assets_skipped_no_sales,
                    "assets_skipped_http_error": result.assets_skipped_http_error,
                },
            )
    except Exception:
        logger.exception("ebay_web_sold_failed")
        with SessionLocal() as _log_session:
            finish_run(_log_session, _run_id, status="error", errors=1)
        send_discord_alert("error", "ebay-web-sold job failed", "check logs")
    finally:
        with SessionLocal() as _log_session:
            prune_old_runs(_log_session, JOB_EBAY_WEB_SOLD)
```

- [ ] **Step 4: Register the job in `create_scheduler`**

Find the block that registers `JOB_CARDMARKET` (around the `if settings.cardmarket_ingest_enabled:` block) and add the `ebay-web-sold` registration immediately after:

```python
    if settings.ebay_web_sold_enabled:
        scheduler.add_job(
            _run_ebay_web_sold,
            "interval",
            hours=24,
            id=JOB_EBAY_WEB_SOLD,
            max_instances=1,
            coalesce=True,
            next_run_time=None,
        )
        prepare_scheduler_for_startup(
            scheduler,
            [JOB_EBAY_WEB_SOLD],
            _STARTUP_DELAY.get(JOB_EBAY_WEB_SOLD, 870),
        )
```

- [ ] **Step 5: Add to heartbeat monitoring**

Find the `_monitored_jobs` list in `_send_heartbeat` (around line 411). Add `JOB_EBAY_WEB_SOLD`:

```python
_monitored_jobs = [JOB_EBAY, JOB_INGESTION, JOB_BULK_REFRESH, JOB_SIGNALS, JOB_YGO, JOB_CARDMARKET, JOB_EXPLANATION, JOB_DIGEST, JOB_TRIAL_EXPIRY, JOB_SEALED_INGEST, JOB_EBAY_WEB_SOLD]
```

- [ ] **Step 6: Verify import chain**

```bash
python -c "from backend.app.backstage.scheduler import create_scheduler; print('ok')"
```

Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add backend/app/backstage/scheduler.py
git commit -m "feat(ebay-web-sold): wire scheduler job — 24h interval, kill switch, heartbeat monitoring"
```

---

## Task 5: Add source weight to signal config

**Files:**
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: Add `ebay_web_sold` to the default source weights string**

Find `signal_delta_source_weights` in `backend/app/core/config.py` and update:

```python
signal_delta_source_weights: str = Field(
    default="pokemon_tcg_api=1.0,ygoprodeck_api=1.0,cardmarket_avg7=1.0,cardmarket_avg30=0.5,cardmarket_avg1=0.0,cardmarket_trend=0.0,ebay_web_sold=1.0"
)
```

- [ ] **Step 2: Verify weight parses correctly**

```bash
python -c "
from backend.app.services.signal_service import _parse_source_weights
w = _parse_source_weights('pokemon_tcg_api=1.0,ygoprodeck_api=1.0,cardmarket_avg7=1.0,cardmarket_avg30=0.5,cardmarket_avg1=0.0,cardmarket_trend=0.0,ebay_web_sold=1.0')
print(w)
assert w['ebay_web_sold'] == 1.0
print('ok')
"
```

Expected: dict printed, then `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/config.py
git commit -m "feat(ebay-web-sold): add ebay_web_sold=1.0 to signal_delta_source_weights"
```

---

## Task 6: Verify end-to-end (local smoke test)

**No new files — runtime verification only.**

- [ ] **Step 1: Run the full test suite to check for regressions**

```bash
python -m pytest tests/ -x -q 2>&1 | tail -20
```

Expected: all existing tests pass; 16 new tests pass.

- [ ] **Step 2: Run a local one-shot scrape against production DB via Railway**

```bash
railway run python -c "
from backend.app.db.base import SessionLocal
from backend.app.ingestion.ebay_web_scrape import ingest_ebay_web_sold
from backend.app.models.asset import Asset
from sqlalchemy import select

with SessionLocal() as session:
    # Limit to 3 assets for smoke test
    assets = session.scalars(
        select(Asset).where(Asset.game=='yugioh', Asset.variant.isnot(None)).limit(3)
    ).all()
    ids = [a.id for a in assets]
    print(f'Testing with {len(ids)} assets: {[(a.name, a.variant) for a in assets]}')
    result = ingest_ebay_web_sold(session, asset_ids=ids)
    print(f'written={result.price_points_written} no_sales={result.assets_skipped_no_sales} http_err={result.assets_skipped_http_error}')
"
```

Expected: `written=2` or `written=3` (some assets may have no EN singles page); no `http_err` greater than 0 unless eBay blocks.

- [ ] **Step 3: Verify rows in production price_history**

```bash
railway run psql "$DATABASE_URL" -c "
SELECT a.name, a.card_number, a.variant, ph.price, ph.captured_at
FROM price_history ph JOIN assets a ON ph.asset_id = a.id
WHERE ph.source = 'ebay_web_sold'
ORDER BY ph.captured_at DESC LIMIT 10;
"
```

Expected: rows with the 3 asset names, prices in $1–$50 range, `captured_at` = now.

- [ ] **Step 4: Commit smoke-test evidence note to PR description**

Document the output of Steps 2 and 3 in the PR body under "Verified by".

---

## Task 7: Enable in production (separate deploy)

**This task is intentionally deferred** — do not run during the initial PR.

When the operator is ready to enable:

```bash
# Set in Railway environment variables:
EBAY_WEB_SOLD_ENABLED=true
```

Then verify after first run:
```bash
railway run psql "$DATABASE_URL" -c "
SELECT job_name, status, records_written, errors, started_at, finished_at
FROM scheduler_run_log
WHERE job_name = 'ebay-web-sold'
ORDER BY started_at DESC LIMIT 5;
"
```

---

## Self-Review

### Spec coverage

| Requirement | Covered by |
|-------------|-----------|
| Rarity-based search query | `_build_search_url` (Task 3) |
| EN singles filter | `_filter_valid_singles` (Task 3) |
| Sealed / multi-qty / graded filter | `_filter_valid_singles` (Task 3) |
| Median aggregation | `_median_price` (Task 3) |
| Write to `price_history` with `ebay_web_sold` | `ingest_ebay_web_sold` (Task 3) |
| Kill switch Category β | `ebay_web_sold_enabled = Field(default=False)` (Task 2) |
| Scheduler job + run log | `_run_ebay_web_sold` (Task 4) |
| Heartbeat monitoring | `_monitored_jobs` update (Task 4) |
| Signal engine source weight | `ebay_web_sold=1.0` in default (Task 5) |
| Startup delay in `_STARTUP_DELAY` | 870s entry (Task 4) |

### No placeholder scan

No TBDs, no "fill in details", no "similar to above" — all code is complete and self-contained.

### Type consistency

- `ingest_ebay_web_sold` returns `EbayWebScrapeResult` — used in `_run_ebay_web_sold` as `result`
- `_extract_sold_items` returns `list[dict]` with keys `sold_date`, `title`, `price_usd` — consumed by `_filter_valid_singles` and `_median_price`
- `_build_search_url` takes `str, str, str` — called with `asset.name`, `asset.card_number`, `asset.variant`
- `_median_price` takes `list[Decimal]` and returns `Decimal` — prices are already `Decimal` from `_extract_sold_items`
