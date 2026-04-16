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
        with patch.dict(os.environ, {"BACKFILL_BATCH_SIZE": "25"}):
            from backend.app.core import config as c
            import importlib
            importlib.reload(c)
            self.assertEqual(c.Settings().backfill_batch_size, 25)


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
