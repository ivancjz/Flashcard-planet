"""Real eBay client — fetches recently sold Pokemon card listings.

Uses the Finding API (findCompletedItems + SoldItemsOnly) as primary source
and falls back to the Browse API for active/ending-soon listings when the
Finding API returns nothing.

Requires EBAY_APP_ID and EBAY_CERT_ID in settings (or env).
Set EBAY_STUB_MODE=false (or unset) to activate.
"""
from __future__ import annotations

import base64
import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

import httpx

from backend.app.core.config import settings
from backend.app.ingestion.ebay.models import EbayListing
from backend.app.models.game import GAME_CONFIG, Game

logger = logging.getLogger(__name__)

_FINDING_API_URL = "https://svcs.ebay.com/services/search/FindingService/v1"
_OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
_BROWSE_API_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
_FINDING_XML_NS = "{urn:ebay:apis:eBLBaseComponents}"


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)


async def _get_token(client: httpx.AsyncClient) -> str:
    credentials = base64.b64encode(
        f"{settings.ebay_app_id}:{settings.ebay_cert_id}".encode()
    ).decode()
    resp = await client.post(
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


def _find_xml_text(node: ElementTree.Element, *parts: str) -> str:
    current: ElementTree.Element | None = node
    for part in parts:
        if current is None:
            return ""
        current = current.find(f"{_FINDING_XML_NS}{part}")
    return (current.text or "").strip() if current is not None else ""


def _parse_finding_xml(xml_text: str) -> list[EbayListing]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    search_result = root.find(f"{_FINDING_XML_NS}searchResult")
    if search_result is None:
        return []
    listings: list[EbayListing] = []
    for item in search_result.findall(f"{_FINDING_XML_NS}item"):
        title = _find_xml_text(item, "title")
        item_id = _find_xml_text(item, "itemId")
        end_time = _find_xml_text(item, "listingInfo", "endTime")
        price = _find_xml_text(item, "sellingStatus", "convertedCurrentPrice")
        if not title or not end_time or not price:
            continue
        sold_at = _parse_iso(end_time)
        if sold_at is None:
            continue
        try:
            price_usd = Decimal(price)
        except InvalidOperation:
            continue
        listings.append(
            EbayListing(
                source_listing_id=item_id or f"ebay-{len(listings)}",
                raw_title=title,
                price_usd=price_usd,
                sold_at=sold_at,
                currency_original="USD",
                url=f"https://www.ebay.com/itm/{item_id}" if item_id else None,
            )
        )
    return listings


def _parse_browse_json(data: dict, limit: int) -> list[EbayListing]:
    listings: list[EbayListing] = []
    for item in data.get("itemSummaries", [])[:limit]:
        title = item.get("title", "")
        item_id = item.get("itemId", "")
        date = item.get("itemEndDate") or item.get("lastSoldDate", "")
        price_info = item.get("price", {})
        price = price_info.get("value", "") if isinstance(price_info, dict) else ""
        if not title or not date or not price:
            continue
        sold_at = _parse_iso(date)
        if sold_at is None:
            continue
        try:
            price_usd = Decimal(price)
        except InvalidOperation:
            continue
        listings.append(
            EbayListing(
                source_listing_id=item_id or f"ebay-browse-{len(listings)}",
                raw_title=title,
                price_usd=price_usd,
                sold_at=sold_at,
                currency_original="USD",
                url=f"https://www.ebay.com/itm/{item_id}" if item_id else None,
            )
        )
    return listings


class RealEbayClient:
    """Fetches recently sold Pokemon card listings from the eBay API.

    Primary: Finding API findCompletedItems (sold prices, XML).
    Fallback: Browse API (ending-soon active listings, JSON).
    """

    async def fetch_sold_listings(self, game: Game, limit: int = 100) -> list[EbayListing]:
        if not settings.ebay_app_id or not settings.ebay_cert_id:
            logger.warning("ebay_real_client_skipped: missing ebay_app_id or ebay_cert_id")
            return []

        meta = GAME_CONFIG[game]
        keywords = " ".join(meta.ebay_search_terms) or settings.ebay_search_keywords or "trading card"
        category_id = meta.ebay_category_id  # None = keyword-only search

        async with httpx.AsyncClient(timeout=20.0) as client:
            # OAuth token (needed for Browse fallback)
            try:
                token = await _get_token(client)
            except Exception:
                logger.exception("ebay_oauth_failed")
                return []

            # --- Primary: Finding API (real sold prices) ---
            listings: list[EbayListing] = []
            try:
                params: dict = {
                    "OPERATION-NAME": "findCompletedItems",
                    "SERVICE-VERSION": "1.0.0",
                    "SECURITY-APPNAME": settings.ebay_app_id,
                    "RESPONSE-DATA-FORMAT": "XML",
                    "keywords": keywords,
                    "itemFilter(0).name": "SoldItemsOnly",
                    "itemFilter(0).value": "true",
                    "sortOrder": "EndTimeSoonest",
                    "paginationInput.entriesPerPage": str(min(limit, 100)),
                }
                if category_id is not None:
                    params["categoryId"] = category_id
                resp = await client.get(_FINDING_API_URL, params=params, timeout=20.0)
                if "10001" in resp.text:
                    logger.warning("ebay_finding_quota_hit")
                elif resp.status_code == 200:
                    listings = _parse_finding_xml(resp.text)
            except Exception:
                logger.exception("ebay_finding_request_failed")

            # --- Fallback: Browse API ---
            if not listings:
                try:
                    browse_params: dict = {
                        "q": keywords,
                        "filter": "buyingOptions:{FIXED_PRICE}",
                        "sort": "endingSoonest",
                        "limit": str(min(limit, 200)),
                    }
                    if category_id is not None:
                        browse_params["category_ids"] = category_id
                    resp = await client.get(
                        _BROWSE_API_URL,
                        headers={
                            "Authorization": f"Bearer {token}",
                            "X-EBAY-C-MARKETPLACE-ID": "EBAY_US",
                        },
                        params=browse_params,
                        timeout=20.0,
                    )
                    resp.raise_for_status()
                    listings = _parse_browse_json(resp.json(), limit)
                except Exception:
                    logger.exception("ebay_browse_request_failed")

        return listings[:limit]
