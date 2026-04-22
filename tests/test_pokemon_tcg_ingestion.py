from datetime import UTC, datetime, timezone
from decimal import Decimal
from email.utils import format_datetime
from unittest import TestCase
from unittest.mock import ANY, Mock, patch

import httpx

from backend.app.ingestion.game_data.base import CardMetadata
from backend.app.ingestion.game_data.registry import GameDataClientRegistry
from backend.app.ingestion.pokemon_tcg import (
    PricePointInsertResult,
    _parse_retry_after,
    ingest_game_cards,
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
            result = ingest_game_cards(
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

        result = ingest_game_cards(
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

        result = ingest_game_cards(
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


def _make_response(retry_after: str | None) -> httpx.Response:
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return httpx.Response(429, headers=headers)


class ParseRetryAfterTests(TestCase):
    def test_numeric_string_returns_float(self):
        self.assertEqual(_parse_retry_after(_make_response("120")), 120.0)

    def test_absent_header_returns_none(self):
        self.assertIsNone(_parse_retry_after(_make_response(None)))

    def test_garbage_string_returns_none(self):
        self.assertIsNone(_parse_retry_after(_make_response("not-a-date")))

    def test_http_date_returns_seconds_until_that_time(self):
        fixed_now = datetime(2026, 4, 22, 12, 0, 0, tzinfo=UTC)
        target = datetime(2026, 4, 22, 12, 0, 30, tzinfo=UTC)
        http_date = format_datetime(target, usegmt=True)
        response = _make_response(http_date)
        with patch(
            "backend.app.ingestion.pokemon_tcg.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = fixed_now
            result = _parse_retry_after(response)
        self.assertAlmostEqual(result, 30.0, places=1)

    def test_http_date_in_the_past_returns_zero(self):
        fixed_now = datetime(2026, 4, 22, 12, 1, 0, tzinfo=UTC)
        target = datetime(2026, 4, 22, 12, 0, 0, tzinfo=UTC)
        http_date = format_datetime(target, usegmt=True)
        response = _make_response(http_date)
        with patch(
            "backend.app.ingestion.pokemon_tcg.datetime"
        ) as mock_dt:
            mock_dt.now.return_value = fixed_now
            result = _parse_retry_after(response)
        self.assertEqual(result, 0.0)


class IngestRegistryFallbackTests(TestCase):
    """ingest_game_cards must not require the registry to be pre-populated."""

    def setUp(self):
        GameDataClientRegistry.clear()

    def tearDown(self):
        GameDataClientRegistry.clear()

    @patch("backend.app.ingestion.game_data.pokemon_client.PokemonClient")
    def test_uses_fallback_client_when_registry_empty(self, MockPokemonClient):
        mock_instance = Mock()
        mock_instance.fetch_card_by_external_id.return_value = None  # card not found → cards_failed
        mock_instance.rate_limit_per_second = 5.0
        MockPokemonClient.return_value = mock_instance

        result = ingest_game_cards(Mock(), card_ids=["sv8pt5-161"], clear_sample_seed=False)

        self.assertEqual(result.cards_requested, 1)
        MockPokemonClient.assert_called_once()
