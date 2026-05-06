"""
tests/test_bulk_refresh_429.py

Regression tests for the 2026-05-04 throughput collapse in _run_bulk_set_price_refresh.
Root cause: _sleep_for_retry had no cap on Retry-After — a Retry-After: 3600 header
caused 3600s sleep per retry × multiple pages × 25 sets = hours of stall.

Fix: _sleep_for_retry now delegates to cap_and_backoff (from pokemon_tcg.py),
which caps Retry-After at 60 seconds.
"""
import unittest
from unittest.mock import MagicMock, patch

import requests


class BulkRefreshCascadeCapTests(unittest.TestCase):

    @staticmethod
    def _make_response(retry_after_value: str | None) -> MagicMock:
        r = MagicMock(spec=requests.Response)
        headers = {}
        if retry_after_value is not None:
            headers["Retry-After"] = retry_after_value
        r.headers = headers
        return r

    def test_retry_after_3600_capped_total_sleep(self):
        """3 consecutive _sleep_for_retry calls with Retry-After: 3600 must total ≤ 180s.

        Before fix: 3 × 3600 = 10,800s. After fix: 3 × 60 = 180s.
        This directly reproduces the 2026-05-04 bulk-refresh stall scenario.
        """
        from scripts.import_pokemon_cards import PokemonTCGImporter
        importer = PokemonTCGImporter.__new__(PokemonTCGImporter)
        response = self._make_response("3600")

        total_slept = 0.0
        with patch("scripts.import_pokemon_cards.time") as mock_time:
            mock_time.sleep.side_effect = lambda secs: None
            for attempt in range(1, 4):  # 3 retry attempts
                importer._sleep_for_retry(response, attempt=attempt)
                total_slept += mock_time.sleep.call_args[0][0]

        self.assertLessEqual(
            total_slept, 180.0,
            f"Total sleep was {total_slept}s — cap not applied (pre-fix would be 10,800s)",
        )

    def test_retry_budget_exhausted_raises_not_hangs(self):
        """_get_json must raise HTTPError after MAX_FETCH_ATTEMPTS, not loop forever.

        This ensures the scheduler catches the exception and writes status='error'
        to scheduler_run_log rather than hanging indefinitely.
        """
        from scripts.import_pokemon_cards import PokemonTCGImporter
        from backend.app.ingestion.pokemon_tcg import MAX_FETCH_ATTEMPTS

        importer = PokemonTCGImporter.__new__(PokemonTCGImporter)
        importer.base_url = "https://api.pokemontcg.io/v2"
        importer.summary = MagicMock()
        importer.summary.cards_seen = 0
        importer.limit = None

        bad_response = MagicMock(spec=requests.Response)
        bad_response.status_code = 429
        bad_response.headers = {"Retry-After": "1"}
        bad_response.raise_for_status.side_effect = requests.HTTPError(response=bad_response)

        mock_session = MagicMock()
        mock_session.get.return_value = bad_response
        importer.session = mock_session

        with patch("scripts.import_pokemon_cards.time"):
            with self.assertRaises(requests.HTTPError):
                importer._get_json("/cards", params={"q": "set.id:base1"})

        # Confirm it tried exactly MAX_FETCH_ATTEMPTS times, not more
        self.assertEqual(mock_session.get.call_count, MAX_FETCH_ATTEMPTS)

    def test_happy_path_200_unaffected(self):
        """A 200 response returns data normally — cap_and_backoff change must not regress this."""
        from scripts.import_pokemon_cards import PokemonTCGImporter

        importer = PokemonTCGImporter.__new__(PokemonTCGImporter)
        importer.base_url = "https://api.pokemontcg.io/v2"
        importer.summary = MagicMock()
        importer.summary.cards_seen = 0
        importer.limit = None

        good_response = MagicMock(spec=requests.Response)
        good_response.status_code = 200
        good_response.headers = {}
        good_response.raise_for_status.return_value = None
        good_response.json.return_value = {"data": [{"id": "base1-4", "name": "Charizard"}], "totalCount": 1, "count": 1, "pageSize": 250}

        mock_session = MagicMock()
        mock_session.get.return_value = good_response
        importer.session = mock_session

        with patch("scripts.import_pokemon_cards.time"):
            result = importer._get_json("/cards", params={"q": "set.id:base1"})

        self.assertEqual(result["data"][0]["name"], "Charizard")
        mock_session.get.assert_called_once()
