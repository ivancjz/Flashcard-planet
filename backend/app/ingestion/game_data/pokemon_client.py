from __future__ import annotations

import logging

import httpx

from backend.app.ingestion.game_data.base import CardMetadata, SetMetadata
from backend.app.ingestion.pokemon_tcg import (
    build_headers,
    fetch_card,
)
from backend.app.models.game import Game

logger = logging.getLogger(__name__)

_SIZE_TO_IMAGE_KEY = {
    "normal": "small",
    "large": "large",
}


class PokemonClient:
    """GameDataClient implementation for the Pokemon TCG API."""

    game = Game.POKEMON
    rate_limit_per_second = 5.0

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    def fetch_card_by_external_id(self, external_id: str) -> CardMetadata | None:
        try:
            with httpx.Client(timeout=20.0, headers=build_headers()) as client:
                raw = fetch_card(client, external_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        return self._to_card_metadata(raw)

    def fetch_cards_by_set(self, set_code: str) -> list[CardMetadata]:
        raise NotImplementedError("fetch_cards_by_set available in TASK-009+")

    def list_sets(self) -> list[SetMetadata]:
        raise NotImplementedError("list_sets available in TASK-009+")

    def get_image_url(self, card: CardMetadata, size: str = "normal") -> str | None:
        images = card.raw_payload.get("images") or {}
        key = _SIZE_TO_IMAGE_KEY.get(size, "small")
        return images.get(key) or None

    def _to_card_metadata(self, raw: dict) -> CardMetadata:
        return CardMetadata(
            external_id=raw["id"],
            name=raw["name"],
            set_code=raw.get("set", {}).get("id", ""),
            set_name=raw.get("set", {}).get("name", ""),
            collector_number=raw.get("number", ""),
            rarity=raw.get("rarity"),
            image_url=(raw.get("images") or {}).get("large"),
            game=Game.POKEMON,
            raw_payload=raw,
        )
