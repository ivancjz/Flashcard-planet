"""
tests/ingestion/game_data/test_registry.py

Covers:
  a. register + get round-trip
  b. get unregistered game raises ValueError
  c. all_live_games filters by GAME_CONFIG status
  d. clear() resets state
"""
from __future__ import annotations

import pytest

from backend.app.models.game import Game


# ---------------------------------------------------------------------------
# Minimal mock client that structurally satisfies GameDataClient Protocol
# ---------------------------------------------------------------------------

class _MockClient:
    def __init__(self, game: Game):
        self._game = game

    @property
    def game(self) -> Game:
        return self._game

    @property
    def rate_limit_per_second(self) -> float:
        return 1.0

    def fetch_card_by_external_id(self, external_id: str):
        return None

    def fetch_cards_by_set(self, set_code: str):
        return []

    def list_sets(self):
        return []

    def get_image_url(self, card, size: str = "normal"):
        return None


# ---------------------------------------------------------------------------
# a. register + get
# ---------------------------------------------------------------------------

class TestRegistryRegisterGet:
    def setup_method(self):
        from backend.app.ingestion.game_data.registry import GameDataClientRegistry
        GameDataClientRegistry.clear()

    def test_register_then_get_returns_same_instance(self):
        from backend.app.ingestion.game_data.registry import GameDataClientRegistry
        client = _MockClient(Game.POKEMON)
        GameDataClientRegistry.register(client)
        assert GameDataClientRegistry.get(Game.POKEMON) is client

    def test_register_overwrites_previous_client(self):
        from backend.app.ingestion.game_data.registry import GameDataClientRegistry
        first = _MockClient(Game.POKEMON)
        second = _MockClient(Game.POKEMON)
        GameDataClientRegistry.register(first)
        GameDataClientRegistry.register(second)
        assert GameDataClientRegistry.get(Game.POKEMON) is second


# ---------------------------------------------------------------------------
# b. get unregistered raises ValueError
# ---------------------------------------------------------------------------

class TestRegistryGetUnregistered:
    def setup_method(self):
        from backend.app.ingestion.game_data.registry import GameDataClientRegistry
        GameDataClientRegistry.clear()

    def test_get_unregistered_game_raises(self):
        from backend.app.ingestion.game_data.registry import GameDataClientRegistry
        with pytest.raises(ValueError, match="yugioh"):
            GameDataClientRegistry.get(Game.YUGIOH)

    def test_error_message_lists_registered_games(self):
        from backend.app.ingestion.game_data.registry import GameDataClientRegistry
        GameDataClientRegistry.register(_MockClient(Game.POKEMON))
        with pytest.raises(ValueError, match="pokemon"):
            GameDataClientRegistry.get(Game.YUGIOH)


# ---------------------------------------------------------------------------
# c. all_live_games
# ---------------------------------------------------------------------------

class TestRegistryAllLiveGames:
    def setup_method(self):
        from backend.app.ingestion.game_data.registry import GameDataClientRegistry
        GameDataClientRegistry.clear()

    def test_all_live_games_returns_only_live_status(self):
        from backend.app.ingestion.game_data.registry import GameDataClientRegistry
        GameDataClientRegistry.register(_MockClient(Game.POKEMON))   # live
        GameDataClientRegistry.register(_MockClient(Game.YUGIOH))    # live (activated in Phase 2)
        GameDataClientRegistry.register(_MockClient(Game.MTG))       # coming_soon
        live = GameDataClientRegistry.all_live_games()
        assert Game.POKEMON in live
        assert Game.YUGIOH in live
        assert Game.MTG not in live

    def test_all_live_games_empty_when_no_clients_registered(self):
        from backend.app.ingestion.game_data.registry import GameDataClientRegistry
        assert GameDataClientRegistry.all_live_games() == []


# ---------------------------------------------------------------------------
# d. clear
# ---------------------------------------------------------------------------

class TestRegistryClear:
    def test_clear_removes_all_clients(self):
        from backend.app.ingestion.game_data.registry import GameDataClientRegistry
        GameDataClientRegistry.register(_MockClient(Game.POKEMON))
        GameDataClientRegistry.clear()
        with pytest.raises(ValueError):
            GameDataClientRegistry.get(Game.POKEMON)
