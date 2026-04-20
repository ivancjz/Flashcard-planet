"""
tests/conftest.py

Shared pytest fixtures for all tests.
"""
from __future__ import annotations

import pytest

from backend.app.models.game import Game


class MockGameDataClient:
    """Minimal GameDataClient-compatible mock for testing.

    Usage (TASK-009 YGO and beyond):
        from tests.conftest import MockGameDataClient
        client = MockGameDataClient(game=Game.YUGIOH)
        GameDataClientRegistry.register(client)

    Override fetch_card_by_external_id to return specific CardMetadata:
        client.card_responses["ygo-123"] = CardMetadata(...)
    """

    def __init__(self, game: Game = Game.POKEMON) -> None:
        self._game = game
        self.card_responses: dict = {}
        self.set_responses: list = []
        self.sets_list: list = []

    @property
    def game(self) -> Game:
        return self._game

    @property
    def rate_limit_per_second(self) -> float:
        return 100.0

    def fetch_card_by_external_id(self, external_id: str):
        return self.card_responses.get(external_id)

    def fetch_cards_by_set(self, set_code: str):
        return self.set_responses

    def list_sets(self):
        return self.sets_list

    def get_image_url(self, card, size: str = "normal"):
        images = (card.raw_payload or {}).get("images", {})
        key = "small" if size == "normal" else "large"
        return images.get(key)


@pytest.fixture
def mock_game_client():
    """Returns a MockGameDataClient for Game.POKEMON. Customize via attributes."""
    return MockGameDataClient(game=Game.POKEMON)
