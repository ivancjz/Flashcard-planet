from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def _log_json(level: int, event: str, **fields: object) -> None:
    logger.log(level, json.dumps({"event": event, **fields}, default=str, sort_keys=True))


@dataclass(frozen=True, slots=True)
class CatalogCard:
    external_id: str
    name: str
    set_name: str | None
    card_number: str | None
    language: str | None
    year: int | None
    normalized_key: str


class PokemonCatalog:
    def __init__(self) -> None:
        self._cache: list[CatalogCard] = []
        self._lookup: dict[str, list[CatalogCard]] = {}
        self._last_loaded_at: datetime | None = None
        self._lock = threading.Lock()
        self._ttl = timedelta(hours=24)
        self._url = os.getenv(
            "POKEMONTCG_CATALOG_URL",
            "https://api.pokemontcg.io/v2/cards?q=supertype:Pok%C3%A9mon&pageSize=250",
        )
        self._timeout = float(os.getenv("POKEMONTCG_CATALOG_TIMEOUT_SECONDS", "20"))
        self._api_key = os.getenv("POKEMONTCG_API_KEY", "")

    def get_cards(self) -> list[CatalogCard]:
        self.refresh_if_needed()
        return list(self._cache)

    def get_lookup(self) -> dict[str, list[CatalogCard]]:
        self.refresh_if_needed()
        return dict(self._lookup)

    def refresh_if_needed(self) -> None:
        with self._lock:
            now = datetime.now(UTC)
            if self._last_loaded_at is not None and now - self._last_loaded_at < self._ttl and self._cache:
                return
            self._refresh_locked()

    def _refresh_locked(self) -> None:
        headers: dict[str, str] = {}
        if self._api_key:
            headers["X-Api-Key"] = self._api_key
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(self._url, headers=headers)
                response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            _log_json(
                logging.WARNING,
                "catalog_refresh_failed",
                error_type=type(exc).__name__,
                message=str(exc),
                used_stale_cache=bool(self._cache),
            )
            return

        cards = [_parse_card(item) for item in payload.get("data", [])]
        cards = [card for card in cards if card is not None]
        if not cards:
            _log_json(logging.WARNING, "catalog_refresh_empty")
            return

        lookup: dict[str, list[CatalogCard]] = {}
        for card in cards:
            lookup.setdefault(card.normalized_key, []).append(card)

        self._cache = cards
        self._lookup = lookup
        self._last_loaded_at = datetime.now(UTC)
        _log_json(logging.INFO, "catalog_refreshed", cards=len(cards))


def _parse_card(item: dict[str, Any]) -> CatalogCard | None:
    external_id = item.get("id")
    name = item.get("name")
    if not external_id or not name:
        return None
    set_name = item.get("set", {}).get("name")
    release_date = item.get("set", {}).get("releaseDate")
    year = None
    if isinstance(release_date, str) and len(release_date) >= 4 and release_date[:4].isdigit():
        year = int(release_date[:4])
    card_number = item.get("number")
    normalized_key = build_catalog_key(name=name, set_name=set_name, card_number=card_number)
    return CatalogCard(
        external_id=external_id,
        name=name,
        set_name=set_name,
        card_number=card_number,
        language="EN",
        year=year,
        normalized_key=normalized_key,
    )


def build_catalog_key(name: str, set_name: str | None, card_number: str | None) -> str:
    tokens = [normalize_catalog_text(name)]
    if set_name:
        tokens.append(normalize_catalog_text(set_name))
    if card_number:
        tokens.append(card_number.casefold())
    return " | ".join(token for token in tokens if token)


def normalize_catalog_text(value: str) -> str:
    return " ".join("".join(ch if ch.isalnum() else " " for ch in value.casefold()).split())


_CATALOG = PokemonCatalog()


def get_catalog() -> PokemonCatalog:
    return _CATALOG
