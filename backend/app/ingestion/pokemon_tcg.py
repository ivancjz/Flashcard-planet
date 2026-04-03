from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.price_sources import POKEMON_TCG_PRICE_SOURCE, SAMPLE_PRICE_SOURCE
from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory

logger = logging.getLogger(__name__)

PRICE_TYPE_PRIORITY = (
    "normal",
    "holofoil",
    "reverseHolofoil",
    "1stEditionHolofoil",
    "1stEditionNormal",
    "unlimitedHolofoil",
    "unlimitedNormal",
)
PRICE_VALUE_PRIORITY = ("market", "mid", "low")
RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
MAX_FETCH_ATTEMPTS = 3


class ProviderUnavailableError(RuntimeError):
    """Raised when the upstream Pokemon TCG API is unavailable after retries."""


@dataclass
class PricePointInsertResult:
    inserted: bool
    previous_price: Decimal | None = None
    price_changed: bool | None = None


@dataclass
class IngestionResult:
    cards_requested: int = 0
    cards_processed: int = 0
    cards_failed: int = 0
    cards_skipped_no_price: int = 0
    assets_created: int = 0
    assets_updated: int = 0
    price_points_inserted: int = 0
    price_points_changed: int = 0
    price_points_unchanged: int = 0
    price_points_skipped_existing_timestamp: int = 0
    sample_rows_deleted: int = 0
    inserted_asset_names: list[str] = field(default_factory=list)
    latest_captured_at: datetime | None = None


def parse_card_ids(raw_card_ids: str) -> list[str]:
    return [card_id.strip() for card_id in raw_card_ids.split(",") if card_id.strip()]


def build_headers() -> dict[str, str]:
    settings = get_settings()
    headers = {"Accept": "application/json"}
    if settings.pokemon_tcg_api_key:
        headers["X-Api-Key"] = settings.pokemon_tcg_api_key
    return headers


def normalize_variant(price_type: str) -> str:
    return price_type.replace("Holofoil", " Holofoil").replace("Edition", " Edition").title()


def parse_release_year(card: dict[str, Any]) -> int | None:
    release_date = card.get("set", {}).get("releaseDate")
    if not release_date:
        return None

    for date_format in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(release_date, date_format).year
        except ValueError:
            continue

    logger.warning(
        "Could not parse Pokemon TCG release date %r for card %s.",
        release_date,
        card.get("id"),
    )
    return None


def choose_price_snapshot(card: dict[str, Any]) -> tuple[str, str, Decimal] | None:
    tcgplayer = card.get("tcgplayer") or {}
    prices = tcgplayer.get("prices") or {}

    for price_type in PRICE_TYPE_PRIORITY:
        bucket = prices.get(price_type)
        if not bucket:
            continue

        for field_name in PRICE_VALUE_PRIORITY:
            value = bucket.get(field_name)
            if value is None:
                continue
            return price_type, field_name, Decimal(str(value))

    return None


def build_asset_payload(card: dict[str, Any], price_type: str, price_field: str) -> dict[str, Any]:
    card_id = card["id"]
    return {
        "asset_class": "TCG",
        "category": "Pokemon",
        "name": card["name"],
        "set_name": card.get("set", {}).get("name"),
        "card_number": card.get("number"),
        "year": parse_release_year(card),
        "language": "EN",
        "variant": normalize_variant(price_type),
        "grade_company": None,
        "grade_score": None,
        "external_id": f"pokemontcg:{card_id}:{price_type}",
        "metadata_json": {
            "provider": POKEMON_TCG_PRICE_SOURCE,
            "provider_card_id": card_id,
            "provider_price_type": price_type,
            "provider_price_field": price_field,
            "rarity": card.get("rarity"),
            "set_id": card.get("set", {}).get("id"),
            "set_series": card.get("set", {}).get("series"),
            "set_release_date": card.get("set", {}).get("releaseDate"),
            "image_small": card.get("images", {}).get("small"),
            "image_large": card.get("images", {}).get("large"),
            "tcgplayer_url": card.get("tcgplayer", {}).get("url"),
        },
        "notes": "Imported from Pokemon TCG API.",
    }


def get_or_create_asset(session: Session, asset_payload: dict[str, Any]) -> tuple[Asset, bool]:
    existing = session.scalar(select(Asset).where(Asset.external_id == asset_payload["external_id"]))
    if existing:
        for key, value in asset_payload.items():
            setattr(existing, key, value)
        return existing, False

    asset = Asset(**asset_payload)
    session.add(asset)
    session.flush()
    return asset, True


def add_price_point(
    session: Session,
    asset_id,
    source: str,
    currency: str,
    price: Decimal,
    captured_at: datetime,
) -> PricePointInsertResult:
    already_exists = session.scalar(
        select(PriceHistory).where(
            PriceHistory.asset_id == asset_id,
            PriceHistory.source == source,
            PriceHistory.captured_at == captured_at,
        )
    )
    if already_exists:
        return PricePointInsertResult(inserted=False)

    previous_row = session.execute(
        select(PriceHistory.price)
        .where(
            PriceHistory.asset_id == asset_id,
            PriceHistory.source == source,
        )
        .order_by(PriceHistory.captured_at.desc())
        .limit(1)
    ).first()
    previous_price = Decimal(previous_row.price) if previous_row is not None else None

    session.add(
        PriceHistory(
            asset_id=asset_id,
            source=source,
            currency=currency,
            price=price,
            captured_at=captured_at,
        )
    )
    return PricePointInsertResult(
        inserted=True,
        previous_price=previous_price,
        price_changed=(previous_price != price) if previous_price is not None else None,
    )

def fetch_card(client: httpx.Client, card_id: str) -> dict[str, Any]:
    settings = get_settings()
    last_exception: Exception | None = None
    url = f"{settings.pokemon_tcg_api_base_url.rstrip('/')}/cards/{card_id}"

    for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
        try:
            response = client.get(url)
            if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_FETCH_ATTEMPTS:
                delay_seconds = min(2 ** (attempt - 1), 8)
                logger.warning(
                    "Retrying Pokemon TCG card %s after HTTP %s on attempt %s/%s.",
                    card_id,
                    response.status_code,
                    attempt,
                    MAX_FETCH_ATTEMPTS,
                )
                time.sleep(delay_seconds)
                continue
            response.raise_for_status()
            payload = response.json()
            return payload["data"]
        except httpx.HTTPStatusError as exc:
            last_exception = exc
            status_code = exc.response.status_code
            if status_code in RETRYABLE_STATUS_CODES and attempt < MAX_FETCH_ATTEMPTS:
                delay_seconds = min(2 ** (attempt - 1), 8)
                logger.warning(
                    "Retrying Pokemon TCG card %s after HTTP %s on attempt %s/%s.",
                    card_id,
                    status_code,
                    attempt,
                    MAX_FETCH_ATTEMPTS,
                )
                time.sleep(delay_seconds)
                continue
            if status_code in RETRYABLE_STATUS_CODES:
                raise ProviderUnavailableError(
                    f"Pokemon TCG API returned HTTP {status_code} for card {card_id} after retries."
                ) from exc
            raise
        except (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError) as exc:
            last_exception = exc
            if attempt < MAX_FETCH_ATTEMPTS:
                delay_seconds = min(2 ** (attempt - 1), 8)
                logger.warning(
                    "Retrying Pokemon TCG card %s after network error on attempt %s/%s: %s",
                    card_id,
                    attempt,
                    MAX_FETCH_ATTEMPTS,
                    exc,
                )
                time.sleep(delay_seconds)
                continue
            raise ProviderUnavailableError(
                f"Pokemon TCG API is unreachable for card {card_id} after retries."
            ) from exc

    raise RuntimeError(f"Failed to fetch card {card_id}") from last_exception


def ingest_pokemon_tcg_cards(
    session: Session,
    card_ids: list[str] | None = None,
    *,
    clear_sample_seed: bool = True,
) -> IngestionResult:
    settings = get_settings()
    configured_card_ids = card_ids or parse_card_ids(settings.pokemon_tcg_card_ids)
    if not configured_card_ids:
        raise ValueError("POKEMON_TCG_CARD_IDS must contain at least one card id.")

    result = IngestionResult(cards_requested=len(configured_card_ids))

    if clear_sample_seed:
        delete_result = session.execute(delete(PriceHistory).where(PriceHistory.source == SAMPLE_PRICE_SOURCE))
        result.sample_rows_deleted = int(delete_result.rowcount or 0)

    ingested_at = datetime.now(UTC).replace(microsecond=0)
    result.latest_captured_at = ingested_at

    with httpx.Client(timeout=20.0, headers=build_headers()) as client:
        for card_id in configured_card_ids:
            try:
                card = fetch_card(client, card_id)
                chosen_price = choose_price_snapshot(card)
                if chosen_price is None:
                    logger.warning("Skipping card %s because no usable tcgplayer price was returned.", card_id)
                    result.cards_skipped_no_price += 1
                    continue

                price_type, price_field, price = chosen_price
                asset_payload = build_asset_payload(card, price_type, price_field)
                asset, created = get_or_create_asset(session, asset_payload)
                if created:
                    result.assets_created += 1
                else:
                    result.assets_updated += 1

                insert_result = add_price_point(
                    session,
                    asset.id,
                    source=POKEMON_TCG_PRICE_SOURCE,
                    currency="USD",
                    price=price,
                    captured_at=ingested_at,
                )
                if insert_result.inserted:
                    result.price_points_inserted += 1
                    if insert_result.price_changed is True:
                        result.price_points_changed += 1
                    elif insert_result.price_changed is False:
                        result.price_points_unchanged += 1
                    if asset.name not in result.inserted_asset_names:
                        result.inserted_asset_names.append(asset.name)
                else:
                    result.price_points_skipped_existing_timestamp += 1

                result.cards_processed += 1
            except ProviderUnavailableError as exc:
                result.cards_failed += 1
                logger.error(
                    "Stopping Pokemon TCG ingestion early because the provider is unavailable while fetching card %s: %s",
                    card_id,
                    exc,
                )
                break
            except Exception:
                result.cards_failed += 1
                logger.exception("Failed to ingest Pokemon TCG card %s. Continuing with the remaining cards.", card_id)

    session.commit()
    logger.info(
        "Pokemon TCG ingest summary: cards_requested=%s cards_processed=%s cards_failed=%s cards_skipped_no_price=%s assets_created=%s assets_updated=%s price_points_inserted=%s price_points_changed=%s price_points_unchanged=%s price_points_skipped_existing_timestamp=%s sample_rows_deleted=%s inserted_assets=%s latest_captured_at=%s",
        result.cards_requested,
        result.cards_processed,
        result.cards_failed,
        result.cards_skipped_no_price,
        result.assets_created,
        result.assets_updated,
        result.price_points_inserted,
        result.price_points_changed,
        result.price_points_unchanged,
        result.price_points_skipped_existing_timestamp,
        result.sample_rows_deleted,
        ", ".join(result.inserted_asset_names) if result.inserted_asset_names else "<none>",
        result.latest_captured_at.isoformat() if result.latest_captured_at else "<none>",
    )
    return result
