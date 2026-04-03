from decimal import Decimal
from unittest import TestCase
from unittest.mock import ANY, MagicMock, Mock, patch

from backend.app.ingestion.pokemon_tcg import (
    PricePointInsertResult,
    ingest_pokemon_tcg_cards,
)
from backend.app.services.observation_match_service import ObservationMatchResult


def make_card(*, card_id: str) -> dict[str, object]:
    return {
        "id": card_id,
        "name": "Umbreon ex",
        "number": "161",
        "set": {
            "name": "Prismatic Evolutions",
            "releaseDate": "2025-01-17",
        },
    }


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
    def _mock_http_client(self):
        client_context = MagicMock()
        client_context.__enter__.return_value = Mock()
        client_context.__exit__.return_value = False
        return client_context

    @patch("backend.app.ingestion.pokemon_tcg.httpx.Client")
    @patch("backend.app.ingestion.pokemon_tcg.stage_observation_match")
    @patch("backend.app.ingestion.pokemon_tcg.choose_price_snapshot")
    @patch("backend.app.ingestion.pokemon_tcg.fetch_card")
    def test_ingestion_logs_unmatched_no_price_observation_and_skips_price_history(
        self,
        fetch_card_mock,
        choose_price_snapshot_mock,
        stage_observation_match_mock,
        client_mock,
    ):
        session = Mock()
        client_mock.return_value = self._mock_http_client()
        fetch_card_mock.return_value = make_card(card_id="sv8pt5-161")
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

    @patch("backend.app.ingestion.pokemon_tcg.httpx.Client")
    @patch("backend.app.ingestion.pokemon_tcg.add_price_point")
    @patch("backend.app.ingestion.pokemon_tcg.stage_observation_match")
    @patch("backend.app.ingestion.pokemon_tcg.choose_price_snapshot")
    @patch("backend.app.ingestion.pokemon_tcg.fetch_card")
    def test_only_matched_observations_write_price_history(
        self,
        fetch_card_mock,
        choose_price_snapshot_mock,
        stage_observation_match_mock,
        add_price_point_mock,
        client_mock,
    ):
        session = Mock()
        client_mock.return_value = self._mock_http_client()
        fetch_card_mock.return_value = make_card(card_id="sv8pt5-161")
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

    @patch("backend.app.ingestion.pokemon_tcg.httpx.Client")
    @patch("backend.app.ingestion.pokemon_tcg.add_price_point")
    @patch("backend.app.ingestion.pokemon_tcg.stage_observation_match")
    @patch("backend.app.ingestion.pokemon_tcg.choose_price_snapshot")
    @patch("backend.app.ingestion.pokemon_tcg.fetch_card")
    def test_ingestion_writes_price_history_after_matched_observation(
        self,
        fetch_card_mock,
        choose_price_snapshot_mock,
        stage_observation_match_mock,
        add_price_point_mock,
        client_mock,
    ):
        session = Mock()
        client_mock.return_value = self._mock_http_client()
        fetch_card_mock.return_value = make_card(card_id="sv8pt5-161")
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
