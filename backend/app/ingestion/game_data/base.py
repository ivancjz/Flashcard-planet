from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from backend.app.models.game import Game


@dataclass(frozen=True)
class CardMetadata:
    """Game-agnostic card metadata returned by every GameDataClient."""
    external_id: str
    name: str
    set_code: str
    set_name: str
    collector_number: str
    rarity: str | None
    image_url: str | None
    game: Game
    raw_payload: dict


@dataclass(frozen=True)
class SetMetadata:
    """Game-agnostic set/expansion metadata."""
    set_code: str
    set_name: str
    release_date: str | None
    total_cards: int | None
    game: Game
    raw_payload: dict


@runtime_checkable
class GameDataClient(Protocol):
    """Protocol every game data source must implement."""

    @property
    def game(self) -> Game: ...

    @property
    def rate_limit_per_second(self) -> float: ...

    def fetch_card_by_external_id(self, external_id: str) -> CardMetadata | None: ...

    def fetch_cards_by_set(self, set_code: str) -> list[CardMetadata]: ...

    def list_sets(self) -> list[SetMetadata]: ...

    def get_image_url(self, card: CardMetadata, size: str = "normal") -> str | None: ...
