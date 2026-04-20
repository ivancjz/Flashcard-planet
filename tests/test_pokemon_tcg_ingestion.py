from decimal import Decimal
from unittest import TestCase
from unittest.mock import ANY, Mock, patch

from backend.app.ingestion.game_data.base import CardMetadata
from backend.app.ingestion.game_data.registry import GameDataClientRegistry
from backend.app.ingestion.pokemon_tcg import (
    PricePointInsertResult,
    ingest_pokemon_tcg_cards,
)
from backend.app.models.game import Game
from backend.app.services.observation_match_service import ObservationMatchResult
from tests.conftest import MockGameDataClient


RAW_CARD = {
    "id": "sv8pt5-161",
    "name": "Umbreon ex",
    "number": "161",
    "set": {
        "id": "sv8pt5",
        "name": "Prismatic Evolutions",
        "releaseDate": "2025-01-17",
    },
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


def make_observation_result(
    *,
    match_status: str,
    can_write_price_history: bool,
    asset_id: int | None = None,
    asset_created: bool = False,
    requires_review: bool = False,
    reason: str = "ok",
) -> ObservationMatchResult:
    matched_asset = None
    if asset_id is not None:
        matched_asset = Mock()
        matched_asset.id = asset_id
        matched_asset.name = "Umbreon ex"

    observation_log = Mock()
    observation_log.match_status = match_status
    observation_log.requires_review = requires_review
    observation_log.reason = reason

    return ObservationMatchResult(
        observation_log=observation_log,
        matched_asset=matched_asset,
        asset_created=asset_created,
        can_write_price_history=can_write_price_history,
    )


class PokemonTcgIngestionTests(TestCase):
    def setUp(self):
        GameDataClientRegistry.clear()
        self._mock_client = MockGameDataClient(game=Game.POKEMON)
        self._mock_client.card_responses["sv8pt5-161"] = CARD_METADATA
        GameDataClientRegistry.register(self._mock_client)

    def tearDown(self):
        GameDataClientRegistry.clear()

    @patch("backend.app.ingestion.pokemon_tcg.stage_observation_match")
    @patch("backend.app.ingestion.pokemon_tcg.choose_price_snapshot")
    def test_ingestion_logs_unmatched_no_price_observation_and_skips_price_history(
        self,
        choose_price_snapshot_mock,
        stage_observation_match_mock,
    ):
        session = Mock()
        choose_price_snapshot_mock.return_value = None
        stage_observation_match_mock.return_value = make_observation_result(
            match_status="unmatched_no_price",
            can_write_price_history=False,
            reason="No usable tcgplayer snapshot.",
        )

        with patch("backend.app.ingestion.pokemon_tcg.add_price_point") as add_price_point_mock:
            result = ingest_pokemon_tcg_cards(
                session,
                card_ids=["sv8pt5-161"],
                clear_sample_seed=False,
            )

        self.assertEqual(result.cards_requested, 1)
        self.assertEqual(result.cards_processed, 0)
        self.assertEqual(result.cards_skipped_no_price, 1)
        self.assertEqual(result.observations_logged, 1)
        self.assertEqual(result.observations_unmatched, 1)
        self.assertEqual(result.observation_match_status_counts, {"unmatched_no_price": 1})
        add_price_point_mock.assert_not_called()
        session.commit.assert_called_once()

    @patch("backend.app.ingestion.pokemon_tcg.add_price_point")
    @patch("backend.app.ingestion.pokemon_tcg.stage_observation_match")
    @patch("backend.app.ingestion.pokemon_tcg.choose_price_snapshot")
    def test_only_matched_observations_write_price_history(
        self,
        choose_price_snapshot_mock,
        stage_observation_match_mock,
        add_price_point_mock,
    ):
        session = Mock()
        choose_price_snapshot_mock.return_value = ("holofoil", "market", Decimal("100.00"))
        stage_observation_match_mock.return_value = make_observation_result(
            match_status="unmatched_ambiguous",
            can_write_price_history=False,
            requires_review=True,
            reason="Multiple canonical matches.",
        )

        result = ingest_pokemon_tcg_cards(
            session,
            card_ids=["sv8pt5-161"],
            clear_sample_seed=False,
        )

        self.assertEqual(result.cards_processed, 0)
        self.assertEqual(result.observations_logged, 1)
        self.assertEqual(result.observations_unmatched, 1)
        self.assertEqual(result.observations_require_review, 1)
        self.assertEqual(result.price_points_inserted, 0)
        add_price_point_mock.assert_not_called()

    @patch("backend.app.ingestion.pokemon_tcg.add_price_point")
    @patch("backend.app.ingestion.pokemon_tcg.stage_observation_match")
    @patch("backend.app.ingestion.pokemon_tcg.choose_price_snapshot")
    def test_ingestion_writes_price_history_after_matched_observation(
        self,
        choose_price_snapshot_mock,
        stage_observation_match_mock,
        add_price_point_mock,
    ):
        session = Mock()
        choose_price_snapshot_mock.return_value = ("holofoil", "market", Decimal("100.00"))
        stage_observation_match_mock.return_value = make_observation_result(
            match_status="matched_existing",
            can_write_price_history=True,
            asset_id=123,
        )
        add_price_point_mock.return_value = PricePointInsertResult(
            inserted=True,
            previous_price=Decimal("95.00"),
            price_changed=True,
        )

        result = ingest_pokemon_tcg_cards(
            session,
            card_ids=["sv8pt5-161"],
            clear_sample_seed=False,
        )

        self.assertEqual(result.cards_processed, 1)
        self.assertEqual(result.assets_updated, 1)
        self.assertEqual(result.price_points_inserted, 1)
        self.assertEqual(result.price_points_changed, 1)
        self.assertEqual(result.observations_logged, 1)
        self.assertEqual(result.observations_matched, 1)
        add_price_point_mock.assert_called_once_with(
            session,
            123,
            source="pokemon_tcg_api",
            currency="USD",
            price=Decimal("100.00"),
            captured_at=ANY,
        )
