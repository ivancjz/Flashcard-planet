"""
tests/test_game_agnostic_ingest.py

Verifies that ingest_game_cards uses GameDataClientRegistry
and routes through the correct game client rather than calling
pokemon_tcg.fetch_card / httpx.Client directly.
"""
from __future__ import annotations

from decimal import Decimal
from unittest import TestCase
from unittest.mock import ANY, MagicMock, Mock, patch

from backend.app.ingestion.game_data.base import CardMetadata
from backend.app.ingestion.game_data.registry import GameDataClientRegistry
from backend.app.models.game import Game
from tests.conftest import MockGameDataClient


RAW_CARD = {
    "id": "sv8pt5-161",
    "name": "Umbreon ex",
    "number": "161",
    "set": {"id": "sv8pt5", "name": "Prismatic Evolutions", "releaseDate": "2025-01-17"},
}

CARD_METADATA = CardMetadata(
    external_id="sv8pt5-161",
    name="Umbreon ex",
    set_code="sv8pt5",
    set_name="Prismatic Evolutions",
    collector_number="161",
    rarity=None,
    image_url=None,
    game=Game.POKEMON,
    raw_payload=RAW_CARD,
)


def _make_observation_result(
    *,
    match_status: str,
    can_write_price_history: bool,
    asset_id: int | None = None,
    asset_created: bool = False,
    requires_review: bool = False,
):
    from backend.app.services.observation_match_service import ObservationMatchResult
    matched_asset = None
    if asset_id is not None:
        matched_asset = Mock()
        matched_asset.id = asset_id
        matched_asset.name = "Umbreon ex"
    obs_log = Mock()
    obs_log.match_status = match_status
    obs_log.requires_review = requires_review
    obs_log.reason = "ok"
    return ObservationMatchResult(
        observation_log=obs_log,
        matched_asset=matched_asset,
        asset_created=asset_created,
        can_write_price_history=can_write_price_history,
    )


class TestIngestUsesRegistry(TestCase):
    def setUp(self):
        GameDataClientRegistry.clear()
        self._mock_client = MockGameDataClient(game=Game.POKEMON)
        self._mock_client.card_responses["sv8pt5-161"] = CARD_METADATA
        GameDataClientRegistry.register(self._mock_client)

    def tearDown(self):
        GameDataClientRegistry.clear()

    # ------------------------------------------------------------------
    # accepts game kwarg
    # ------------------------------------------------------------------

    def test_accepts_game_kwarg(self):
        from backend.app.ingestion.pokemon_tcg import ingest_game_cards
        session = Mock()
        with patch("backend.app.ingestion.pokemon_tcg.choose_price_snapshot", return_value=None), \
             patch("backend.app.ingestion.pokemon_tcg.stage_observation_match") as mock_obs:
            mock_obs.return_value = _make_observation_result(
                match_status="unmatched_no_price", can_write_price_history=False
            )
            result = ingest_game_cards(
                session, card_ids=["sv8pt5-161"], game=Game.POKEMON, clear_sample_seed=False
            )
        self.assertIsNotNone(result)

    # ------------------------------------------------------------------
    # uses registry — fetch_card and httpx.Client are NOT called
    # ------------------------------------------------------------------

    def test_does_not_call_pokemon_tcg_fetch_card(self):
        from backend.app.ingestion.pokemon_tcg import ingest_game_cards
        session = Mock()
        with patch("backend.app.ingestion.pokemon_tcg.fetch_card") as mock_fetch, \
             patch("backend.app.ingestion.pokemon_tcg.choose_price_snapshot", return_value=None), \
             patch("backend.app.ingestion.pokemon_tcg.stage_observation_match") as mock_obs:
            mock_obs.return_value = _make_observation_result(
                match_status="unmatched_no_price", can_write_price_history=False
            )
            ingest_game_cards(
                session, card_ids=["sv8pt5-161"], game=Game.POKEMON, clear_sample_seed=False
            )
        mock_fetch.assert_not_called()

    def test_does_not_create_httpx_client_directly(self):
        from backend.app.ingestion.pokemon_tcg import ingest_game_cards
        session = Mock()
        with patch("backend.app.ingestion.pokemon_tcg.httpx") as mock_httpx, \
             patch("backend.app.ingestion.pokemon_tcg.choose_price_snapshot", return_value=None), \
             patch("backend.app.ingestion.pokemon_tcg.stage_observation_match") as mock_obs:
            mock_obs.return_value = _make_observation_result(
                match_status="unmatched_no_price", can_write_price_history=False
            )
            ingest_game_cards(
                session, card_ids=["sv8pt5-161"], game=Game.POKEMON, clear_sample_seed=False
            )
        mock_httpx.Client.assert_not_called()

    # ------------------------------------------------------------------
    # raw_payload is used as the card dict — existing pipeline unchanged
    # ------------------------------------------------------------------

    def test_cards_processed_via_registry_client(self):
        from backend.app.ingestion.pokemon_tcg import ingest_game_cards, PricePointInsertResult
        session = Mock()
        with patch("backend.app.ingestion.pokemon_tcg.choose_price_snapshot",
                   return_value=("holofoil", "market", Decimal("100.00"))), \
             patch("backend.app.ingestion.pokemon_tcg.stage_observation_match") as mock_obs, \
             patch("backend.app.ingestion.pokemon_tcg.add_price_point") as mock_add:
            mock_obs.return_value = _make_observation_result(
                match_status="matched_existing", can_write_price_history=True, asset_id=42
            )
            mock_add.return_value = PricePointInsertResult(
                inserted=True, previous_price=None, price_changed=None
            )
            result = ingest_game_cards(
                session, card_ids=["sv8pt5-161"], game=Game.POKEMON, clear_sample_seed=False
            )
        self.assertEqual(result.cards_processed, 1)
        self.assertEqual(result.price_points_inserted, 1)

    # ------------------------------------------------------------------
    # ProviderUnavailableError from client still breaks the loop
    # ------------------------------------------------------------------

    def test_provider_unavailable_breaks_loop(self):
        from backend.app.ingestion.pokemon_tcg import ingest_game_cards, ProviderUnavailableError
        self._mock_client.card_responses.clear()

        def raise_unavailable(external_id: str):
            raise ProviderUnavailableError("API down")

        self._mock_client.fetch_card_by_external_id = raise_unavailable

        session = Mock()
        result = ingest_game_cards(
            session, card_ids=["sv8pt5-161", "sv8pt5-162"], game=Game.POKEMON, clear_sample_seed=False
        )
        # cards_failed increments once then loop breaks — second card never attempted
        self.assertEqual(result.cards_failed, 1)
        self.assertEqual(result.cards_requested, 2)
