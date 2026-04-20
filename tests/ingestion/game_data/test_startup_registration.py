"""
tests/ingestion/game_data/test_startup_registration.py

Verifies that register_default_clients() wires up PokemonClient in the registry.
"""
from __future__ import annotations

import pytest

from backend.app.models.game import Game


class TestStartupRegistration:
    def setup_method(self):
        from backend.app.ingestion.game_data.registry import GameDataClientRegistry
        GameDataClientRegistry.clear()

    def test_register_default_clients_registers_pokemon(self):
        from backend.app.ingestion.game_data import register_default_clients
        from backend.app.ingestion.game_data.pokemon_client import PokemonClient
        from backend.app.ingestion.game_data.registry import GameDataClientRegistry

        register_default_clients(api_key="test-key")
        client = GameDataClientRegistry.get(Game.POKEMON)
        assert isinstance(client, PokemonClient)

    def test_register_default_clients_pokemon_is_live(self):
        from backend.app.ingestion.game_data import register_default_clients
        from backend.app.ingestion.game_data.registry import GameDataClientRegistry

        register_default_clients(api_key="")
        live = GameDataClientRegistry.all_live_games()
        assert Game.POKEMON in live
