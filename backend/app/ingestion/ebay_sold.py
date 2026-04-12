from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.price_sources import EBAY_SOLD_PRICE_SOURCE, SAMPLE_PRICE_SOURCE
from backend.app.ingestion.pokemon_tcg import IngestionResult
from backend.app.models.asset import Asset
from backend.app.models.observation_match_log import ObservationMatchLog
from backend.app.models.price_history import PriceHistory

logger = logging.getLogger(__name__)

EBAY_FINDING_API_URL = "https://svcs.ebay.com/services/search/FindingService/v1"
EBAY_OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_INSIGHTS_API_URL = "https://api.ebay.com/buy/marketplace_insights/v1_beta/item_sales/search"
EBAY_BROWSE_API_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
EBAY_FINDING_XML_NS = "{urn:ebay:apis:eBLBaseComponents}"
GRADING_KEYWORDS = {"psa", "bgs", "cgc", "sgc", "gma", "ace", "beckett"}


def _log_info(event: str, **fields: object) -> None:
    field_text = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info("%s %s", event, field_text)


def _parse_keywords(raw_keywords: str) -> list[str]:
    return [keyword.strip() for keyword in raw_keywords.split(",") if keyword.strip()]


def _parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _get_app_token(client: httpx.Client) -> str:
    import base64
    credentials = base64.b64encode(
        f"{settings.ebay_app_id}:{settings.ebay_cert_id}".encode()
    ).decode()
    response = client.post(
        EBAY_OAUTH_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
        timeout=15.0,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _parse_insights_items(data: dict) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for item in data.get("itemSales", []):
        title = item.get("title", "")
        item_id = item.get("itemId", "")
        sold_date = item.get("lastSoldDate", "")
        price_info = item.get("lastSoldPrice", {})
        price = price_info.get("value", "") if isinstance(price_info, dict) else ""
        if not title or not sold_date or not price:
            continue
        items.append({"item_id": item_id, "title": title, "captured_at": sold_date, "price": price})
    return items


def _parse_browse_items(data: dict) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for item in data.get("itemSummaries", []):
        title = item.get("title", "")
        item_id = item.get("itemId", "")
        date = item.get("itemEndDate") or item.get("lastSoldDate", "")
        price_info = item.get("price", {})
        price = price_info.get("value", "") if isinstance(price_info, dict) else ""
        if not title or not date or not price:
            continue
        items.append({"item_id": item_id, "title": title, "captured_at": date, "price": price})
    return items


def _find_xml_text(node: ElementTree.Element, *path_parts: str) -> str:
    current: ElementTree.Element | None = node
    for part in path_parts:
        if current is None:
            return ""
        current = current.find(f"{EBAY_FINDING_XML_NS}{part}")
    return (current.text or "").strip() if current is not None else ""


def _parse_finding_items(xml_text: str) -> list[dict[str, str]]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return []
    search_result = root.find(f"{EBAY_FINDING_XML_NS}searchResult")
    if search_result is None:
        return []
    items: list[dict[str, str]] = []
    for item in search_result.findall(f"{EBAY_FINDING_XML_NS}item"):
        title = _find_xml_text(item, "title")
        item_id = _find_xml_text(item, "itemId")
        end_time = _find_xml_text(item, "listingInfo", "endTime")
        price = _find_xml_text(item, "sellingStatus", "convertedCurrentPrice")
        if not title or not end_time or not price:
            continue
        items.append({"item_id": item_id, "title": title, "captured_at": end_time, "price": price})
    return items


def _fetch_finding_completed(client: httpx.Client, query: str) -> list[dict[str, str]] | None:
    """Call findCompletedItems. Returns parsed items, empty list if none, or None on hard error."""
    try:
        resp = client.get(
            EBAY_FINDING_API_URL,
            params={
                "OPERATION-NAME": "findCompletedItems",
                "SERVICE-VERSION": "1.0.0",
                "SECURITY-APPNAME": settings.ebay_app_id,
                "RESPONSE-DATA-FORMAT": "XML",
                "keywords": query,
                "itemFilter(0).name": "SoldItemsOnly",
                "itemFilter(0).value": "true",
                "sortOrder": "EndTimeSoonest",
                "paginationInput.entriesPerPage": "50",
            },
            timeout=20.0,
        )
    except Exception:
        logger.exception("ebay_finding_api_request_failed query=%s", query)
        return None

    # errorId 10001 = quota/rate limit — check body first regardless of status code
    if "10001" in resp.text:
        logger.warning("ebay_finding_api_quota_limit query=%s — will retry next run", query)
        return None

    if resp.status_code != 200:
        logger.warning("ebay_finding_api_bad_status status=%s query=%s", resp.status_code, query)
        return None

    return _parse_finding_items(resp.text)


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _title_contains_card_name(title: str, asset: Asset) -> bool:
    return _normalize(asset.name) in _normalize(title)


def _is_grade_compatible(title: str, asset: Asset) -> bool:
    """Return False when grading keywords in title conflict with the asset's grade status."""
    normalized = _normalize(title)
    title_words = set(normalized.split())
    has_grade_keyword = bool(title_words & GRADING_KEYWORDS)
    if asset.grade_company:
        # Graded asset: title must mention the right company and approximate score.
        company = _normalize(asset.grade_company)
        if not has_grade_keyword:
            return False
        if company not in normalized:
            return False
        if asset.grade_score is not None:
            score_str = str(int(asset.grade_score))
            if score_str not in normalized:
                return False
        return True
    else:
        # Ungraded asset: reject listings that mention any grading company.
        return not has_grade_keyword


def _iqr_bounds(prices: list[Decimal]) -> tuple[Decimal, Decimal]:
    """Return (lower, upper) IQR-based outlier bounds for a list of prices."""
    sorted_prices = sorted(prices)
    n = len(sorted_prices)
    q1 = sorted_prices[n // 4]
    q3 = sorted_prices[(3 * n) // 4]
    iqr = q3 - q1
    multiplier = Decimal("1.5")
    return q1 - multiplier * iqr, q3 + multiplier * iqr


def _build_search_query(asset: Asset) -> str:
    parts = ["Pokemon", asset.name]
    if asset.set_name:
        parts.append(asset.set_name)
    if asset.grade_company and asset.grade_score:
        parts.append(f"{asset.grade_company} {int(asset.grade_score)}")
    return " ".join(parts)


def ingest_ebay_sold_cards(
    session: Session,
    card_ids: list[str] | None = None,
    max_assets: int | None = None,
    *,
    clear_sample_seed: bool = False,
) -> IngestionResult:
    if settings.ebay_app_id == "" or settings.ebay_cert_id == "":
        return IngestionResult()

    all_assets_in_db = list(session.scalars(select(Asset)).all())

    if card_ids is not None:
        # Preserve the caller-supplied order (scheduler pre-sorts by priority).
        id_to_asset = {
            key: asset
            for asset in all_assets_in_db
            for key in (str(asset.id), asset.external_id or "")
            if key
        }
        all_assets = [
            id_to_asset[cid.strip()]
            for cid in card_ids
            if cid.strip() in id_to_asset
        ]
        # Deduplicate while preserving order (an asset can appear via both id forms).
        seen: set[object] = set()
        ordered: list[Asset] = []
        for a in all_assets:
            if a.id not in seen:
                seen.add(a.id)
                ordered.append(a)
        all_assets = ordered
    else:
        all_assets = all_assets_in_db
        # Budget guard: cap to max_assets, prioritising least-recently ingested first.
        if max_assets is not None and len(all_assets) > max_assets:
            all_assets.sort(
                key=lambda a: (a.metadata_json or {}).get("ebay_sold_last_ingested_at") or ""
            )
            _log_info(
                "ebay_sold_budget_guard_applied",
                pool_size=len(all_assets),
                effective_limit=max_assets,
            )
            all_assets = all_assets[:max_assets]

    if not all_assets:
        return IngestionResult()

    result = IngestionResult(cards_requested=len(all_assets))
    if clear_sample_seed:
        delete_result = session.execute(delete(PriceHistory).where(PriceHistory.source == SAMPLE_PRICE_SOURCE))
        result.sample_rows_deleted = int(delete_result.rowcount or 0)

    now = datetime.now(UTC).replace(microsecond=0)
    lookback_cutoff = now - timedelta(hours=settings.ebay_sold_lookback_hours)
    metadata_cutoff = now - timedelta(hours=24)
    matched_asset_ids: set[object] = set()

    with httpx.Client(timeout=20.0) as client:
        try:
            token = _get_app_token(client)
            result.api_calls_used += 1  # OAuth token request
        except Exception:
            logger.exception("ebay_sold_oauth_token_failed")
            return result

        for asset in all_assets:
            query = _build_search_query(asset)
            _log_info("ebay_sold_asset_fetch_started", asset_id=asset.id, name=asset.name, query=query)

            raw_listings: list[dict[str, str]] = []
            api_used = "finding"

            # 1. Try findCompletedItems (real sold prices — buggy but preferred when it works)
            finding_results = _fetch_finding_completed(client, query)
            result.api_calls_used += 1  # Finding API request (attempted regardless of outcome)
            if finding_results:
                raw_listings = finding_results

            # 2. Fall back to Browse API if Finding returned nothing or errored
            if not raw_listings:
                api_used = "browse"
                try:
                    resp = client.get(
                        EBAY_BROWSE_API_URL,
                        headers={"Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
                        params={
                            "q": query,
                            "category_ids": "2536",
                            "filter": "buyingOptions:{FIXED_PRICE}",
                            "sort": "endingSoonest",
                            "limit": "50",
                        },
                    )
                    resp.raise_for_status()
                    raw_listings = _parse_browse_items(resp.json())
                    result.api_calls_used += 1  # Browse API request
                except Exception:
                    result.api_calls_used += 1  # Browse API request (failed)
                    result.cards_failed += 1
                    logger.exception("ebay_sold_asset_fetch_failed asset_id=%s name=%s", asset.id, asset.name)
                    continue

            _log_info(
                "ebay_sold_asset_fetch_completed",
                asset_id=asset.id,
                name=asset.name,
                api=api_used,
                listings_returned=len(raw_listings),
            )
            result.cards_processed += 1

            # --- Filter: card name in title + grade compatibility ---
            candidates: list[tuple[dict[str, str], datetime, Decimal]] = []
            for listing in raw_listings:
                captured_at = _parse_iso_datetime(listing["captured_at"])
                if captured_at is None or captured_at < lookback_cutoff:
                    continue
                if not _title_contains_card_name(listing["title"], asset):
                    result.observations_unmatched += 1
                    result.observation_match_status_counts["unmatched_name_not_in_title"] = (
                        result.observation_match_status_counts.get("unmatched_name_not_in_title", 0) + 1
                    )
                    continue
                if not _is_grade_compatible(listing["title"], asset):
                    result.observations_unmatched += 1
                    result.observation_match_status_counts["unmatched_grade_mismatch"] = (
                        result.observation_match_status_counts.get("unmatched_grade_mismatch", 0) + 1
                    )
                    continue
                try:
                    price = Decimal(listing["price"])
                except InvalidOperation:
                    result.cards_failed += 1
                    logger.warning("ebay_sold_listing_invalid_price title=%s price=%s", listing["title"], listing["price"])
                    continue
                candidates.append((listing, captured_at, price))

            # --- IQR outlier removal (only when 4+ candidates) ---
            if len(candidates) >= 4:
                prices = [p for _, _, p in candidates]
                lower, upper = _iqr_bounds(prices)
                before = len(candidates)
                candidates = [(l, c, p) for l, c, p in candidates if lower <= p <= upper]
                removed = before - len(candidates)
                if removed:
                    result.observation_match_status_counts["unmatched_iqr_outlier"] = (
                        result.observation_match_status_counts.get("unmatched_iqr_outlier", 0) + removed
                    )
                    _log_info("ebay_sold_iqr_filtered", asset_id=asset.id, name=asset.name, removed=removed)

            for listing, captured_at, price in candidates:
                result.latest_captured_at = max(
                    filter(None, [result.latest_captured_at, captured_at]),
                    default=captured_at,
                )
                result.observations_logged += 1
                result.observations_matched += 1
                result.observation_match_status_counts["matched_existing"] = (
                    result.observation_match_status_counts.get("matched_existing", 0) + 1
                )
                matched_asset_ids.add(asset.id)

                # Dedup 1 — stable external item ID (preferred)
                item_id = listing.get("item_id", "")
                if item_id:
                    already_observed = session.scalar(
                        select(ObservationMatchLog.id).where(
                            ObservationMatchLog.provider == EBAY_SOLD_PRICE_SOURCE,
                            ObservationMatchLog.external_item_id == item_id,
                        )
                    )
                    if already_observed is not None:
                        result.price_points_skipped_existing_timestamp += 1
                        result.observation_match_status_counts["duplicates_skipped_item_id"] = (
                            result.observation_match_status_counts.get("duplicates_skipped_item_id", 0) + 1
                        )
                        continue

                # Dedup 2 — fallback: (asset_id, source, captured_at)
                already_exists = session.scalar(
                    select(PriceHistory.id).where(
                        PriceHistory.asset_id == asset.id,
                        PriceHistory.source == EBAY_SOLD_PRICE_SOURCE,
                        PriceHistory.captured_at == captured_at,
                    )
                )
                if already_exists is not None:
                    result.price_points_skipped_existing_timestamp += 1
                    result.observation_match_status_counts["duplicates_skipped_timestamp"] = (
                        result.observation_match_status_counts.get("duplicates_skipped_timestamp", 0) + 1
                    )
                    continue

                session.add(
                    PriceHistory(
                        asset_id=asset.id,
                        source=EBAY_SOLD_PRICE_SOURCE,
                        currency="USD",
                        price=price,
                        captured_at=captured_at,
                    )
                )
                session.add(
                    ObservationMatchLog(
                        provider=EBAY_SOLD_PRICE_SOURCE,
                        external_item_id=listing["item_id"],
                        raw_title=listing["title"],
                        matched_asset_id=asset.id,
                        match_status="matched",
                        confidence=Decimal("1.00"),
                        reason=f"Searched by asset name via {api_used} API; grade-compatible; passed IQR filter.",
                        requires_review=False,
                        created_at=captured_at,
                    )
                )
                result.price_points_inserted += 1
                if asset.name not in result.inserted_asset_names:
                    result.inserted_asset_names.append(asset.name)
                _log_info(
                    "ebay_sold_listing_inserted",
                    asset_id=asset.id,
                    name=asset.name,
                    price=price,
                    captured_at=captured_at.isoformat(),
                )

    if matched_asset_ids:
        matched_assets = session.scalars(select(Asset).where(Asset.id.in_(matched_asset_ids))).all()
        for asset in matched_assets:
            sale_count_24h = int(
                session.scalar(
                    select(func.count(PriceHistory.id)).where(
                        PriceHistory.asset_id == asset.id,
                        PriceHistory.source == EBAY_SOLD_PRICE_SOURCE,
                        PriceHistory.captured_at >= metadata_cutoff,
                    )
                )
                or 0
            )
            asset.metadata_json = {
                **(asset.metadata_json or {}),
                "ebay_sold_24h_count": sale_count_24h,
                "ebay_sold_last_ingested_at": now.isoformat(),
            }

    session.commit()
    _log_info(
        "ebay_sold_ingest_summary",
        cards_requested=result.cards_requested,
        cards_processed=result.cards_processed,
        cards_failed=result.cards_failed,
        price_points_inserted=result.price_points_inserted,
        price_points_skipped_existing_timestamp=result.price_points_skipped_existing_timestamp,
        observations_logged=result.observations_logged,
        observations_matched=result.observations_matched,
        observations_unmatched=result.observations_unmatched,
        api_calls_used=result.api_calls_used,
        latest_captured_at=result.latest_captured_at.isoformat() if result.latest_captured_at else "<none>",
    )
    return result
