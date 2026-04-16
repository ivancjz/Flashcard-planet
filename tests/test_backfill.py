"""Tests for the backfill pass (missing prices + images)."""
from __future__ import annotations

import unittest


class BackfillConfigTests(unittest.TestCase):
    def test_backfill_batch_size_default(self):
        from backend.app.core.config import get_settings
        s = get_settings()
        self.assertEqual(s.backfill_batch_size, 100)

    def test_backfill_batch_size_respects_env(self):
        import os
        from unittest.mock import patch
        from backend.app.core.config import Settings
        with patch.dict(os.environ, {"BACKFILL_BATCH_SIZE": "25"}):
            self.assertEqual(Settings().backfill_batch_size, 25)


class BackfillFunctionTests(unittest.TestCase):
    def test_run_backfill_pass_is_callable(self):
        from backend.app.ingestion.pokemon_tcg import run_backfill_pass
        self.assertTrue(callable(run_backfill_pass))

    def test_backfill_result_has_expected_fields(self):
        from backend.app.ingestion.pokemon_tcg import BackfillResult
        r = BackfillResult()
        self.assertEqual(r.missing_price, 0)
        self.assertEqual(r.missing_image, 0)
        self.assertEqual(r.attempted, 0)
        self.assertEqual(r.price_filled, 0)
        self.assertEqual(r.image_filled, 0)
        self.assertEqual(r.skipped_no_price, 0)
        self.assertEqual(r.errors, 0)


class BackfillQueryTests(unittest.TestCase):
    def test_query_missing_price_returns_card_ids(self):
        """_query_missing_price must return provider_card_id strings."""
        from unittest.mock import MagicMock, patch
        from backend.app.ingestion.pokemon_tcg import _query_missing_price

        mock_session = MagicMock()
        mock_row = MagicMock()
        mock_row.provider_card_id = "base1-4"
        mock_session.execute.return_value.all.return_value = [mock_row]

        result = _query_missing_price(mock_session, limit=10, primary_source="pokemon_tcg_api")
        self.assertEqual(result, ["base1-4"])

    def test_query_missing_image_returns_card_ids(self):
        """_query_missing_image must return provider_card_id strings."""
        from unittest.mock import MagicMock
        from backend.app.ingestion.pokemon_tcg import _query_missing_image

        mock_session = MagicMock()
        mock_row = MagicMock()
        mock_row.provider_card_id = "base1-6"
        mock_session.execute.return_value.all.return_value = [mock_row]

        result = _query_missing_image(mock_session, limit=10)
        self.assertEqual(result, ["base1-6"])


class RunBackfillPassTests(unittest.TestCase):
    def test_returns_backfill_result_when_no_gaps(self):
        """run_backfill_pass returns a BackfillResult with zeros when no gaps exist."""
        from unittest.mock import MagicMock, patch
        from backend.app.ingestion.pokemon_tcg import run_backfill_pass

        mock_session = MagicMock()

        with patch("backend.app.ingestion.pokemon_tcg._query_missing_price", return_value=[]) as mp, \
             patch("backend.app.ingestion.pokemon_tcg._query_missing_image", return_value=[]) as mi:
            result = run_backfill_pass(mock_session)

        self.assertEqual(result.attempted, 0)
        self.assertEqual(result.missing_price, 0)
        self.assertEqual(result.missing_image, 0)

    def test_returns_backfill_result_with_counts_when_gaps_exist(self):
        """run_backfill_pass attempts re-ingestion for cards in the gap lists."""
        from unittest.mock import MagicMock, patch
        from backend.app.ingestion.pokemon_tcg import run_backfill_pass, BackfillResult

        mock_session = MagicMock()
        fake_card = {
            "id": "base1-4",
            "name": "Charizard",
            "images": {"small": "https://example.com/charizard.png"},
            "set": {"name": "Base Set", "id": "base1"},
            "number": "4",
            "tcgplayer": {"prices": {"holofoil": {"market": 350.0}}},
        }

        with patch("backend.app.ingestion.pokemon_tcg._query_missing_price", return_value=["base1-4"]), \
             patch("backend.app.ingestion.pokemon_tcg._query_missing_image", return_value=[]), \
             patch("backend.app.ingestion.pokemon_tcg.fetch_card", return_value=fake_card), \
             patch("backend.app.ingestion.pokemon_tcg.stage_observation_match") as mock_obs, \
             patch("backend.app.ingestion.pokemon_tcg.add_price_point") as mock_price:
            obs_result = MagicMock()
            obs_result.can_write_price_history = True
            obs_result.matched_asset = MagicMock()
            obs_result.matched_asset.id = "some-uuid"
            obs_result.matched_asset.metadata_json = {"images": {"small": "https://example.com/charizard.png"}}
            mock_obs.return_value = obs_result
            mock_price.return_value = MagicMock(inserted=True, price_changed=True)

            result = run_backfill_pass(mock_session)

        self.assertEqual(result.missing_price, 1)
        self.assertEqual(result.attempted, 1)
