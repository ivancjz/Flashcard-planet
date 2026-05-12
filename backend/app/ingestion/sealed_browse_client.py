"""Sealed product from-price ingestion via eBay Browse API.

Dedicated Browse API path — does NOT use noise_filter.py or _is_single_card(),
which actively reject sealed product titles (booster, ETB, sealed box).

Data flow:
  sealed_products.json
        |
        v  upsert Asset rows (asset_class=SEALED)
        |
        v  Browse API search per product
        |
        v  filter: item + shipping price, rank by total, skip rank 1 (outlier guard)
        |
        v  from_price = median(ranks 2-6) when min_count_met (>=5 listings)
        |
        v  write listing_snapshot row
"""
from __future__ import annotations

import base64
import json
import logging
import statistics
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.asset import Asset
from backend.app.models.enums import AssetClass
from backend.app.models.listing_snapshot import ListingSnapshot

logger = logging.getLogger(__name__)

_OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
_BROWSE_API_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
_SEALED_PRODUCTS_JSON = Path(__file__).parent / "sealed_products.json"

# Reference ZIP for shipping cost estimation (New York, NY)
_REFERENCE_ZIP = "10001"

# Minimum listings after outlier filter to compute a valid from_price
_MIN_LISTING_COUNT = 5


@dataclass
class ProductConfig:
    name: str
    set_name: str
    ebay_search_query: str
    product_type: str
    game: str


def load_sealed_products() -> list[ProductConfig]:
    data = json.loads(_SEALED_PRODUCTS_JSON.read_text(encoding="utf-8"))
    return [ProductConfig(**p) for p in data]


def _get_oauth_token(client: httpx.Client) -> str:
    settings = get_settings()
    if not settings.ebay_app_id or not settings.ebay_cert_id:
        raise ValueError(
            "EBAY_APP_ID and EBAY_CERT_ID must be set in environment to run sealed ingest"
        )
    credentials = base64.b64encode(
        f"{settings.ebay_app_id}:{settings.ebay_cert_id}".encode()
    ).decode()
    resp = client.post(
        _OAUTH_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _parse_listing_price(item: dict) -> Decimal | None:
    """Return item price + shipping cost as total landed price, or None on parse error."""
    try:
        item_price = Decimal(str(item.get("price", {}).get("value", "0")))
    except Exception:
        return None

    shipping_cost = Decimal("0")
    shipping_options = item.get("shippingOptions", [])
    if shipping_options:
        try:
            shipping_cost = Decimal(str(shipping_options[0].get("shippingCost", {}).get("value", "0")))
        except Exception:
            pass  # fall back to item price only

    total = item_price + shipping_cost
    return total if total > 0 else None


def _compute_from_price(items: list[dict]) -> tuple[Decimal | None, int, bool, list[dict]]:
    """Compute from_price from Browse API response items.

    Returns (from_price, listing_count, min_count_met, raw_snapshot):
    - from_price: median of ranks 2-6 by total landed price, or None
    - listing_count: total items from API
    - min_count_met: True when >=5 listings passed the filter
    - raw_snapshot: up to 10 listings for debugging
    """
    listing_count = len(items)

    # Build (total_price, item) pairs, skip unparseable
    priced = []
    for item in items:
        total = _parse_listing_price(item)
        if total is not None:
            priced.append((total, item))

    # Sort by total price ascending; rank 1 = cheapest (potential outlier/fake)
    priced.sort(key=lambda x: x[0])

    raw_snapshot = [
        {
            "item_id": p[1].get("itemId", ""),
            "title": p[1].get("title", "")[:120],
            "price": str(p[0]),
            "listing_url": p[1].get("itemWebUrl", ""),
        }
        for p in priced[:10]
    ]

    # Need at least _MIN_LISTING_COUNT listings to compute a reliable from_price
    if len(priced) < _MIN_LISTING_COUNT:
        return None, listing_count, False, raw_snapshot

    # Skip rank 1 (cheapest = likely outlier), use ranks 2-6
    candidate_prices = [p[0] for p in priced[1: _MIN_LISTING_COUNT + 1]]
    from_price = Decimal(str(statistics.median(candidate_prices))).quantize(Decimal("0.01"))

    return from_price, listing_count, True, raw_snapshot


def _fetch_listings_for_product(
    client: httpx.Client,
    token: str,
    product: ProductConfig,
) -> tuple[Decimal | None, int, bool, list[dict]]:
    """Call Browse API for one sealed product. Returns (from_price, listing_count, min_count_met, raw_snapshot).

    Raises on network errors, HTTP failures, or parse errors.
    Caller (run_sealed_ingest) is responsible for per-product exception handling.
    A "no listings" result (min_count_met=False) is a valid return; an exception means the API failed.
    """
    params = {
        "q": product.ebay_search_query,
        "limit": "50",
        "filter": "conditionIds:{1000}",  # New condition only
    }
    resp = client.get(
        _BROWSE_API_URL,
        params=params,
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
            "X-EBAY-C-ENDUSERCTX": f"contextualLocation=country%3DUS%2Czip%3D{_REFERENCE_ZIP}",
        },
        timeout=15.0,
    )
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", "30"))
        logger.warning("sealed_browse_429 product=%s sleeping=%ds", product.name, retry_after)
        time.sleep(min(retry_after, 60))
        resp = client.get(
            _BROWSE_API_URL,
            params=params,
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
                "X-EBAY-C-ENDUSERCTX": f"contextualLocation=country%3DUS%2Czip%3D{_REFERENCE_ZIP}",
            },
            timeout=15.0,
        )
    resp.raise_for_status()
    items = resp.json().get("itemSummaries", [])
    return _compute_from_price(items)


def _upsert_asset(db: Session, product: ProductConfig) -> uuid.UUID:
    """Upsert Asset row for a sealed product. Returns the asset_id."""
    stmt = select(Asset).where(
        Asset.asset_class == AssetClass.SEALED.value,
        Asset.game == product.game,
        Asset.name == product.name,
        Asset.set_name == product.set_name,
    )
    existing = db.scalars(stmt).first()
    if existing:
        return existing.id

    asset = Asset(
        asset_class=AssetClass.SEALED.value,
        game=product.game,
        name=product.name,
        set_name=product.set_name,
        product_type=product.product_type,
    )
    db.add(asset)
    db.flush()
    return asset.id


def run_sealed_ingest(db: Session) -> dict[str, Any]:
    """Main entrypoint for the sealed ingest scheduler job.

    Upserts Asset rows, polls Browse API for each product,
    writes listing_snapshot rows.

    Returns summary dict for scheduler_run_log meta_json.
    """
    settings = get_settings()
    if not settings.ebay_app_id or not settings.ebay_cert_id:
        raise ValueError("EBAY_APP_ID and EBAY_CERT_ID must be configured for sealed ingest")

    products = load_sealed_products()
    now = datetime.now(UTC)

    success_count = 0
    fail_count = 0
    snapshots_written = 0
    failures: list[dict[str, str]] = []

    with httpx.Client() as client:
        try:
            token = _get_oauth_token(client)
        except Exception as exc:
            logger.error("sealed_ingest_oauth_failed error=%s", exc)
            raise

        for product in products:
            try:
                asset_id = _upsert_asset(db, product)

                from_price, listing_count, min_count_met, raw_snapshot = _fetch_listings_for_product(
                    client, token, product
                )

                snapshot = ListingSnapshot(
                    asset_id=asset_id,
                    source="ebay_sealed_ask",
                    captured_at=now,
                    from_price=from_price,
                    listing_count=listing_count,
                    min_count_met=min_count_met,
                    raw_snapshot={"listings": raw_snapshot},
                )
                db.add(snapshot)
                snapshots_written += 1

                if min_count_met:
                    success_count += 1
                    logger.info(
                        "sealed_ingest_ok product=%s from_price=%s listings=%d",
                        product.name, from_price, listing_count,
                    )
                else:
                    logger.warning(
                        "sealed_ingest_insufficient product=%s listings=%d",
                        product.name, listing_count,
                    )

                # Respect Browse API rate limit: ~5 calls/sec
                time.sleep(0.25)

            except Exception as exc:
                fail_count += 1
                failures.append({
                    "product_id": product.name,
                    "error_type": type(exc).__name__,
                    "message": str(exc)[:200],
                })
                logger.error("sealed_ingest_product_failed product=%s error=%s", product.name, exc)

    db.commit()

    summary: dict[str, Any] = {
        "products_total": len(products),
        "products_with_from_price": success_count,
        "products_insufficient_listings": len(products) - success_count - fail_count,
        "products_failed": fail_count,
        "snapshots_written": snapshots_written,
    }
    if failures:
        summary["failures"] = failures
    return summary
