from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
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


@dataclass
class IngestionResult:
    cards_processed: int = 0
    assets_created: int = 0
    assets_updated: int = 0
    price_points_inserted: int = 0
    sample_rows_deleted: int = 0


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
    return datetime.fromisoformat(release_date).year


def parse_provider_updated_at(card: dict[str, Any], fallback: datetime) -> datetime:
    updated_at = card.get("tcgplayer", {}).get("updatedAt")
    if not updated_at:
        return fallback

    parsed = datetime.strptime(updated_at, "%Y/%m/%d").replace(tzinfo=UTC)
    return parsed


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
            "provider": "pokemon_tcg_api",
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
) -> bool:
    already_exists = session.scalar(
        select(PriceHistory).where(
            PriceHistory.asset_id == asset_id,
            PriceHistory.captured_at == captured_at,
        )
    )
    if already_exists:
        return False

    session.add(
        PriceHistory(
            asset_id=asset_id,
            source=source,
            currency=currency,
            price=price,
            captured_at=captured_at,
        )
    )
    return True


def fetch_card(card_id: str) -> dict[str, Any]:
    settings = get_settings()
    with httpx.Client(timeout=20.0, headers=build_headers()) as client:
        response = client.get(f"{settings.pokemon_tcg_api_base_url.rstrip('/')}/cards/{card_id}")
        response.raise_for_status()
        payload = response.json()
    return payload["data"]


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

    result = IngestionResult()

    if clear_sample_seed:
        delete_result = session.execute(delete(PriceHistory).where(PriceHistory.source == "sample_seed"))
        result.sample_rows_deleted = int(delete_result.rowcount or 0)

    ingested_at = datetime.now(UTC).replace(microsecond=0)

    for card_id in configured_card_ids:
        card = fetch_card(card_id)
        chosen_price = choose_price_snapshot(card)
        if chosen_price is None:
            logger.warning("Skipping card %s because no usable tcgplayer price was returned.", card_id)
            continue

        price_type, price_field, price = chosen_price
        asset_payload = build_asset_payload(card, price_type, price_field)
        asset, created = get_or_create_asset(session, asset_payload)
        if created:
            result.assets_created += 1
        else:
            result.assets_updated += 1

        provider_updated_at = parse_provider_updated_at(card, ingested_at)
        if add_price_point(
            session,
            asset.id,
            source="pokemon_tcg_api",
            currency="USD",
            price=price,
            captured_at=provider_updated_at,
        ):
            result.price_points_inserted += 1

        if add_price_point(
            session,
            asset.id,
            source="pokemon_tcg_api",
            currency="USD",
            price=price,
            captured_at=ingested_at,
        ):
            result.price_points_inserted += 1

        result.cards_processed += 1

    session.commit()
    return result
