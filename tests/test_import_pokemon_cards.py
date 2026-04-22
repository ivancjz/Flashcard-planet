"""Tests for scripts/import_pokemon_cards.py, focused on set-ID validation."""
from unittest import TestCase
from unittest.mock import MagicMock, patch

from scripts.import_pokemon_cards import _process_set


def _make_importer(cards: list) -> MagicMock:
    importer = MagicMock()
    importer.fetch_cards_for_set.return_value = cards
    importer._remaining_capacity.return_value = None
    importer._run_captured_at = None
    importer.summary.sets_processed = 0
    return importer


class ProcessSetEmptyCardsTests(TestCase):
    def test_all_sets_mode_empty_cards_is_silent(self):
        """--all-sets: empty card response is a non-fatal skip (some sets genuinely have no cards)."""
        importer = _make_importer(cards=[])
        _process_set(
            importer,
            session=MagicMock(),
            set_id="ghost-set",
            can_record_prices=False,
            dry_run=False,
            asset_batch=[],
            price_batch=[],
            explicit_set_id=False,
        )
        self.assertEqual(importer.summary.sets_processed, 0)

    def test_explicit_set_id_empty_cards_raises(self):
        """--set-ids: empty card response for an explicit set ID must raise, not silently succeed."""
        importer = _make_importer(cards=[])
        with self.assertRaises(ValueError) as ctx:
            _process_set(
                importer,
                session=MagicMock(),
                set_id="swsh1",
                can_record_prices=False,
                dry_run=False,
                asset_batch=[],
                price_batch=[],
                explicit_set_id=True,
            )
        self.assertIn("swsh1", str(ctx.exception))
