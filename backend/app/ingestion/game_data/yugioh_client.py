from __future__ import annotations

import logging

import httpx

from backend.app.ingestion.game_data.base import CardMetadata, SetMetadata
from backend.app.models.game import Game

logger = logging.getLogger(__name__)

_SIZE_TO_IMAGE_KEY = {
    "normal": "image_url",
    "small": "image_url_small",
    "cropped": "image_url_cropped",
}


class YugiohClient:
    """GameDataClient implementation for the YGOPRODeck API."""

    game = Game.YUGIOH
    rate_limit_per_second = 10.0

    BASE_URL = "https://db.ygoprodeck.com/api/v7"

    def __init__(self) -> None:
        self.client = httpx.Client(
            timeout=15.0,
            headers={"User-Agent": "FlashcardPlanet/1.0"},
        )
        self._set_code_map: dict[str, str] | None = None

    def fetch_card_by_external_id(self, external_id: str) -> CardMetadata | None:
        try:
            resp = self.client.get(f"{self.BASE_URL}/cardinfo.php", params={"id": external_id})
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (400, 404):
                return None
            raise
        raw = resp.json()["data"][0]
        return self._to_card_metadata(raw)

    def fetch_cards_by_set(self, set_code: str) -> list[CardMetadata]:
        set_name = self._resolve_set_name(set_code)
        resp = self.client.get(f"{self.BASE_URL}/cardinfo.php", params={"cardset": set_name})
        resp.raise_for_status()
        return [self._to_card_metadata(raw) for raw in resp.json()["data"]]

    def fetch_set_entries(self, set_code: str) -> list[tuple[dict, dict]]:
        """Return (raw_card, set_entry) pairs for a set, filtered to entries with real prices.

        Each pair represents one investable asset: a specific card printing (set_code + rarity)
        with a known market price. Entries where set_price is "0" or missing are skipped.
        """
        set_name = self._resolve_set_name(set_code)
        resp = self.client.get(
            f"{self.BASE_URL}/cardinfo.php",
            params={"cardset": set_name, "misc": "yes"},
        )
        resp.raise_for_status()

        prefix = f"{set_code}-"
        results: list[tuple[dict, dict]] = []
        for raw in resp.json()["data"]:
            for entry in raw.get("card_sets") or []:
                if not entry.get("set_code", "").startswith(prefix):
                    continue
                price_str = entry.get("set_price") or "0"
                try:
                    price = float(price_str)
                except ValueError:
                    continue
                if price <= 0:
                    continue
                results.append((raw, entry))
        return results

    @staticmethod
    def make_external_id(konami_id: int, set_entry_code: str, rarity: str) -> str:
        """Canonical external_id for a YGO asset: yugioh:{konami_id}:{set_code}:{rarity_slug}."""
        rarity_slug = rarity.lower().replace(" ", "_").replace("/", "_")
        return f"yugioh:{konami_id}:{set_entry_code}:{rarity_slug}"

    def _resolve_set_name(self, set_code: str) -> str:
        """Map abbreviated set code to the full name that cardinfo.php's cardset param requires."""
        if self._set_code_map is None:
            resp = self.client.get(f"{self.BASE_URL}/cardsets.php")
            resp.raise_for_status()
            self._set_code_map = {s["set_code"]: s["set_name"] for s in resp.json()}
        if set_code not in self._set_code_map:
            raise ValueError(f"Unknown YuGiOh set code: {set_code!r}")
        return self._set_code_map[set_code]

    def list_sets(self) -> list[SetMetadata]:
        resp = self.client.get(f"{self.BASE_URL}/cardsets.php")
        resp.raise_for_status()
        return [self._to_set_metadata(s) for s in resp.json()]

    def get_image_url(self, card: CardMetadata, size: str = "normal") -> str | None:
        images = card.raw_payload.get("card_images") or []
        if not images:
            return None
        key = _SIZE_TO_IMAGE_KEY.get(size, "image_url")
        return images[0].get(key) or None

    def _to_card_metadata(self, raw: dict) -> CardMetadata:
        card_sets = raw.get("card_sets") or []
        first_set = card_sets[0] if card_sets else None
        card_images = raw.get("card_images") or []
        image_url = card_images[0].get("image_url") if card_images else None
        return CardMetadata(
            external_id=str(raw["id"]),
            name=raw["name"],
            set_code=first_set["set_code"] if first_set else "UNKNOWN",
            set_name=first_set["set_name"] if first_set else "Unknown",
            collector_number="",
            rarity=first_set["set_rarity"] if first_set else None,
            image_url=image_url,
            game=Game.YUGIOH,
            raw_payload=raw,
        )

    def _to_set_metadata(self, raw: dict) -> SetMetadata:
        return SetMetadata(
            set_code=raw["set_code"],
            set_name=raw["set_name"],
            release_date=raw.get("tcg_date"),
            total_cards=raw.get("num_of_cards"),
            game=Game.YUGIOH,
            raw_payload=raw,
        )
