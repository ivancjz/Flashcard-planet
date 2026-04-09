from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
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
EBAY_XML_NS = "{urn:ebay:apis:eBLBaseComponents}"
FUZZY_MATCH_THRESHOLD = 0.65


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


def _find_text(node: ElementTree.Element, path: str) -> str | None:
    current: ElementTree.Element | None = node
    for part in path.split("/"):
        if current is None:
            return None
        current = current.find(f"{EBAY_XML_NS}{part}")
    if current is None or current.text is None:
        return None
    return current.text.strip()


def _parse_listing_items(xml_payload: str) -> list[dict[str, str]]:
    root = ElementTree.fromstring(xml_payload)
    search_result = root.find(f"{EBAY_XML_NS}searchResult")
    if search_result is None:
        return []

    items: list[dict[str, str]] = []
    for item in search_result.findall(f"{EBAY_XML_NS}item"):
        title = _find_text(item, "title")
        item_id = _find_text(item, "itemId") or ""
        end_time = _find_text(item, "listingInfo/endTime")
        price = _find_text(item, "sellingStatus/convertedCurrentPrice")
        if not title or not end_time or not price:
            continue
        items.append(
            {
                "item_id": item_id,
                "title": title,
                "captured_at": end_time,
                "price": price,
            }
        )
    return items


def _normalize_match_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _match_asset(title: str, assets: list[Asset]) -> tuple[Asset | None, float]:
    normalized_title = _normalize_match_text(title)
    best_asset: Asset | None = None
    best_score = 0.0
    for asset in assets:
        score = SequenceMatcher(None, normalized_title, _normalize_match_text(asset.name)).ratio()
        if score > best_score:
            best_asset = asset
            best_score = score
    if best_score >= FUZZY_MATCH_THRESHOLD:
        return best_asset, best_score
    return None, best_score


def ingest_ebay_sold_cards(
    session: Session,
    card_ids: list[str] | None = None,
    *,
    clear_sample_seed: bool = False,
) -> IngestionResult:
    if settings.ebay_app_id == "":
        return IngestionResult()

    keywords = _parse_keywords(settings.ebay_search_keywords)
    if not keywords:
        return IngestionResult()

    result = IngestionResult(cards_requested=len(keywords))
    if clear_sample_seed:
        delete_result = session.execute(delete(PriceHistory).where(PriceHistory.source == SAMPLE_PRICE_SOURCE))
        result.sample_rows_deleted = int(delete_result.rowcount or 0)

    all_assets = session.scalars(select(Asset)).all()
    if card_ids is not None:
        card_id_set = {card_id.strip() for card_id in card_ids if card_id.strip()}
        all_assets = [
            asset
            for asset in all_assets
            if str(asset.id) in card_id_set or (asset.external_id or "") in card_id_set
        ]

    now = datetime.now(UTC).replace(microsecond=0)
    lookback_cutoff = now - timedelta(hours=settings.ebay_sold_lookback_hours)
    metadata_cutoff = now - timedelta(hours=24)
    matched_asset_ids: set[object] = set()

    with httpx.Client(timeout=20.0) as client:
        for keyword in keywords:
            _log_info(
                "ebay_sold_keyword_fetch_started",
                keyword=keyword,
                lookback_hours=settings.ebay_sold_lookback_hours,
            )
            try:
                response = client.get(
                    EBAY_FINDING_API_URL,
                    params={
                        "OPERATION-NAME": "findCompletedItems",
                        "SERVICE-VERSION": "1.0.0",
                        "SECURITY-APPNAME": settings.ebay_app_id,
                        "RESPONSE-DATA-FORMAT": "XML",
                        "keywords": keyword,
                        "itemFilter(0).name": "SoldItemsOnly",
                        "itemFilter(0).value": "true",
                        "itemFilter(1).name": "ListingType",
                        "itemFilter(1).value": "FixedPrice",
                        "sortOrder": "EndTimeSoonest",
                        "paginationInput.entriesPerPage": "100",
                    },
                )
                response.raise_for_status()
            except Exception:
                result.cards_failed += 1
                logger.exception("ebay_sold_keyword_fetch_failed keyword=%s", keyword)
                continue

            listings = _parse_listing_items(response.text)
            _log_info(
                "ebay_sold_keyword_fetch_completed",
                keyword=keyword,
                listings_returned=len(listings),
            )

            for listing in listings:
                captured_at = _parse_iso_datetime(listing["captured_at"])
                if captured_at is None or captured_at < lookback_cutoff:
                    continue

                result.latest_captured_at = max(
                    filter(
                        None,
                        [result.latest_captured_at, captured_at],
                    ),
                    default=captured_at,
                )
                result.observations_logged += 1

                matched_asset, score = _match_asset(listing["title"], all_assets)
                if matched_asset is None:
                    session.add(
                        ObservationMatchLog(
                            provider=EBAY_SOLD_PRICE_SOURCE,
                            external_item_id=listing["item_id"],
                            raw_title=listing["title"],
                            matched_asset_id=None,
                            match_status="unmatched",
                            confidence=Decimal(str(score)).quantize(Decimal("0.01")),
                            reason=f"Fuzzy match score {score:.2f} below threshold {FUZZY_MATCH_THRESHOLD:.2f}.",
                            requires_review=False,
                            created_at=captured_at or datetime.now(UTC),
                        )
                    )
                    result.observations_unmatched += 1
                    result.observation_match_status_counts["unmatched_fuzzy_threshold"] = (
                        result.observation_match_status_counts.get("unmatched_fuzzy_threshold", 0) + 1
                    )
                    _log_info(
                        "ebay_sold_listing_unmatched",
                        title=listing["title"],
                        score=f"{score:.2f}",
                    )
                    continue

                result.cards_processed += 1
                result.observations_matched += 1
                result.observation_match_status_counts["matched_existing"] = (
                    result.observation_match_status_counts.get("matched_existing", 0) + 1
                )
                matched_asset_ids.add(matched_asset.id)

                already_exists = session.scalar(
                    select(PriceHistory.id).where(
                        PriceHistory.asset_id == matched_asset.id,
                        PriceHistory.source == EBAY_SOLD_PRICE_SOURCE,
                        PriceHistory.captured_at == captured_at,
                    )
                )
                if already_exists is not None:
                    result.price_points_skipped_existing_timestamp += 1
                    _log_info(
                        "ebay_sold_listing_duplicate_skipped",
                        asset_id=matched_asset.id,
                        title=listing["title"],
                        captured_at=captured_at.isoformat(),
                    )
                    continue

                try:
                    price = Decimal(listing["price"])
                except InvalidOperation:
                    result.cards_failed += 1
                    logger.warning("ebay_sold_listing_invalid_price title=%s price=%s", listing["title"], listing["price"])
                    continue

                session.add(
                    PriceHistory(
                        asset_id=matched_asset.id,
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
                        matched_asset_id=matched_asset.id,
                        match_status="matched",
                        confidence=Decimal(str(score)).quantize(Decimal("0.01")),
                        reason="Matched eBay sold listing to an existing asset via fuzzy title match.",
                        requires_review=False,
                        created_at=captured_at or datetime.now(UTC),
                    )
                )
                result.price_points_inserted += 1
                if matched_asset.name not in result.inserted_asset_names:
                    result.inserted_asset_names.append(matched_asset.name)
                _log_info(
                    "ebay_sold_listing_inserted",
                    asset_id=matched_asset.id,
                    title=listing["title"],
                    price=price,
                    captured_at=captured_at.isoformat(),
                    score=f"{score:.2f}",
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
        latest_captured_at=result.latest_captured_at.isoformat() if result.latest_captured_at else "<none>",
    )
    return result
