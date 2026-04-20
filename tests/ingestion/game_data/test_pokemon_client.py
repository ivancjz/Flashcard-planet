"""
tests/ingestion/game_data/test_pokemon_client.py

Covers:
  a. PokemonClient structurally satisfies GameDataClient Protocol
  b. game property returns Game.POKEMON
  c. fetch_card_by_external_id returns CardMetadata on valid API response
  d. fetch_card_by_external_id returns None when API returns 404
  e. raw_payload preserved in CardMetadata
  f. CardMetadata fields mapped correctly from API response
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from backend.app.models.game import Game


# Minimal fake API card response
FAKE_CARD_RAW = {
    "id": "sv1-1",
    "name": "Bulbasaur",
    "number": "1",
    "rarity": "Common",
    "images": {
        "small": "https://images.pokemontcg.io/sv1/1.png",
        "large": "https://images.pokemontcg.io/sv1/1_hires.png",
    },
    "set": {
        "id": "sv1",
        "name": "Scarlet & Violet",
        "releaseDate": "2023-03-31",
        "total": 258,
    },
}


# ---------------------------------------------------------------------------
# a/b. Protocol conformance and game property
# ---------------------------------------------------------------------------

class TestPokemonClientProtocol:
    def _make_client(self):
        from backend.app.ingestion.game_data.pokemon_client import PokemonClient
        return PokemonClient(api_key="test-key")

    def test_isinstance_game_data_client_protocol(self):
        from backend.app.ingestion.game_data.base import GameDataClient
        client = self._make_client()
        assert isinstance(client, GameDataClient)

    def test_game_property_is_pokemon(self):
        client = self._make_client()
        assert client.game == Game.POKEMON

    def test_rate_limit_per_second_is_positive(self):
        client = self._make_client()
        assert client.rate_limit_per_second > 0


# ---------------------------------------------------------------------------
# c/d/e/f. fetch_card_by_external_id
# ---------------------------------------------------------------------------

class TestPokemonClientFetchCard:
    def _make_client(self):
        from backend.app.ingestion.game_data.pokemon_client import PokemonClient
        return PokemonClient(api_key="test-key")

    def test_returns_card_metadata_on_success(self):
        from backend.app.ingestion.game_data.base import CardMetadata
        client = self._make_client()
        with patch("backend.app.ingestion.game_data.pokemon_client.fetch_card", return_value=FAKE_CARD_RAW):
            result = client.fetch_card_by_external_id("sv1-1")
        assert isinstance(result, CardMetadata)

    def test_external_id_mapped_correctly(self):
        client = self._make_client()
        with patch("backend.app.ingestion.game_data.pokemon_client.fetch_card", return_value=FAKE_CARD_RAW):
            result = client.fetch_card_by_external_id("sv1-1")
        assert result.external_id == "sv1-1"

    def test_name_mapped_correctly(self):
        client = self._make_client()
        with patch("backend.app.ingestion.game_data.pokemon_client.fetch_card", return_value=FAKE_CARD_RAW):
            result = client.fetch_card_by_external_id("sv1-1")
        assert result.name == "Bulbasaur"

    def test_set_code_mapped_correctly(self):
        client = self._make_client()
        with patch("backend.app.ingestion.game_data.pokemon_client.fetch_card", return_value=FAKE_CARD_RAW):
            result = client.fetch_card_by_external_id("sv1-1")
        assert result.set_code == "sv1"

    def test_set_name_mapped_correctly(self):
        client = self._make_client()
        with patch("backend.app.ingestion.game_data.pokemon_client.fetch_card", return_value=FAKE_CARD_RAW):
            result = client.fetch_card_by_external_id("sv1-1")
        assert result.set_name == "Scarlet & Violet"

    def test_collector_number_mapped_correctly(self):
        client = self._make_client()
        with patch("backend.app.ingestion.game_data.pokemon_client.fetch_card", return_value=FAKE_CARD_RAW):
            result = client.fetch_card_by_external_id("sv1-1")
        assert result.collector_number == "1"

    def test_rarity_mapped_correctly(self):
        client = self._make_client()
        with patch("backend.app.ingestion.game_data.pokemon_client.fetch_card", return_value=FAKE_CARD_RAW):
            result = client.fetch_card_by_external_id("sv1-1")
        assert result.rarity == "Common"

    def test_image_url_uses_large(self):
        client = self._make_client()
        with patch("backend.app.ingestion.game_data.pokemon_client.fetch_card", return_value=FAKE_CARD_RAW):
            result = client.fetch_card_by_external_id("sv1-1")
        assert result.image_url == "https://images.pokemontcg.io/sv1/1_hires.png"

    def test_game_field_is_pokemon(self):
        client = self._make_client()
        with patch("backend.app.ingestion.game_data.pokemon_client.fetch_card", return_value=FAKE_CARD_RAW):
            result = client.fetch_card_by_external_id("sv1-1")
        assert result.game == Game.POKEMON

    def test_raw_payload_fully_preserved(self):
        client = self._make_client()
        with patch("backend.app.ingestion.game_data.pokemon_client.fetch_card", return_value=FAKE_CARD_RAW):
            result = client.fetch_card_by_external_id("sv1-1")
        assert result.raw_payload == FAKE_CARD_RAW

    def test_provider_unavailable_propagates_to_caller(self):
        from backend.app.ingestion.pokemon_tcg import ProviderUnavailableError
        import pytest
        client = self._make_client()
        with patch(
            "backend.app.ingestion.game_data.pokemon_client.fetch_card",
            side_effect=ProviderUnavailableError("API down"),
        ):
            with pytest.raises(ProviderUnavailableError):
                client.fetch_card_by_external_id("sv1-1")

    def test_returns_none_on_404(self):
        import httpx
        client = self._make_client()
        mock_response = MagicMock()
        mock_response.status_code = 404
        with patch(
            "backend.app.ingestion.game_data.pokemon_client.fetch_card",
            side_effect=httpx.HTTPStatusError("not found", request=MagicMock(), response=mock_response),
        ):
            result = client.fetch_card_by_external_id("sv1-1")
        assert result is None


# ---------------------------------------------------------------------------
# get_image_url
# ---------------------------------------------------------------------------

class TestPokemonClientGetImageUrl:
    def _make_client(self):
        from backend.app.ingestion.game_data.pokemon_client import PokemonClient
        return PokemonClient(api_key="test-key")

    def _make_metadata(self, images: dict):
        from backend.app.ingestion.game_data.base import CardMetadata
        raw = {**FAKE_CARD_RAW, "images": images}
        return CardMetadata(
            external_id="sv1-1",
            name="Bulbasaur",
            set_code="sv1",
            set_name="Scarlet & Violet",
            collector_number="1",
            rarity="Common",
            image_url=images.get("large"),
            game=Game.POKEMON,
            raw_payload=raw,
        )

    def test_get_image_url_normal_size(self):
        client = self._make_client()
        card = self._make_metadata({"small": "s.png", "large": "l.png"})
        assert client.get_image_url(card, size="normal") == "s.png"

    def test_get_image_url_large_size(self):
        client = self._make_client()
        card = self._make_metadata({"small": "s.png", "large": "l.png"})
        assert client.get_image_url(card, size="large") == "l.png"

    def test_get_image_url_returns_none_when_missing(self):
        client = self._make_client()
        card = self._make_metadata({})
        assert client.get_image_url(card) is None
