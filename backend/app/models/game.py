from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Game(str, Enum):
    POKEMON = "pokemon"
    YUGIOH = "yugioh"
    MTG = "mtg"
    ONE_PIECE = "one_piece"
    LORCANA = "lorcana"


@dataclass(frozen=True)
class GameMetadata:
    display_name: str
    status: str  # "live" | "beta" | "coming_soon"
    native_franchise: str
    # eBay marketplace category ID for Collectible Card Games sub-categories.
    # None = no dedicated category; client falls back to keyword-only search.
    ebay_category_id: Optional[str] = None
    ebay_search_terms: tuple[str, ...] = field(default_factory=tuple)
    ebay_exclude_terms: tuple[str, ...] = field(default_factory=tuple)


GAME_CONFIG: dict[Game, GameMetadata] = {
    Game.POKEMON: GameMetadata(
        display_name="Pokémon",
        status="live",
        native_franchise="pokemon",
        # eBay: Collectible Card Games > Pokémon > Pokémon Individual Cards
        ebay_category_id="2536",
        ebay_search_terms=("Pokemon TCG", "Pokemon card"),
        ebay_exclude_terms=("proxy", "custom", "fake"),
    ),
    Game.YUGIOH: GameMetadata(
        display_name="Yu-Gi-Oh!",
        status="coming_soon",
        native_franchise="yu_gi_oh",
        # eBay: Collectible Card Games > Yu-Gi-Oh! > Individual Cards
        ebay_category_id="183454",
        ebay_search_terms=("Yu-Gi-Oh card", "YGO TCG"),
        ebay_exclude_terms=("proxy", "custom", "fake"),
    ),
    Game.MTG: GameMetadata(
        display_name="Magic: The Gathering",
        status="coming_soon",
        native_franchise="magic",
        # eBay: Collectible Card Games > Magic: The Gathering > Individual Cards
        ebay_category_id="38292",
        ebay_search_terms=("Magic the Gathering card", "MTG card"),
        ebay_exclude_terms=("proxy", "custom", "fake", "alter"),
    ),
    Game.ONE_PIECE: GameMetadata(
        display_name="One Piece TCG",
        status="coming_soon",
        native_franchise="one_piece",
        # eBay does not have a dedicated One Piece TCG sub-category as of 2025-Q4;
        # falls back to keyword search within the parent CCG category.
        ebay_category_id=None,
        ebay_search_terms=("One Piece TCG card", "One Piece card game"),
        ebay_exclude_terms=("proxy", "custom", "fake"),
    ),
    Game.LORCANA: GameMetadata(
        display_name="Disney Lorcana",
        status="coming_soon",
        native_franchise="lorcana",
        # eBay does not have a dedicated Lorcana sub-category as of 2025-Q4;
        # falls back to keyword search within the parent CCG category.
        ebay_category_id=None,
        ebay_search_terms=("Disney Lorcana card", "Lorcana TCG"),
        ebay_exclude_terms=("proxy", "custom", "fake"),
    ),
}
