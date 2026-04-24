"""
tests/test_signal_delta.py

Unit tests for the Phase 3a signal delta algorithm.

Covers:
  a. _weighted_median — pure function
  b. _parse_source_weights — config parsing
  c. _compute_delta_batch — windowed multi-source delta (mocked DB)
  d. compute_signal_delta — single-asset wrapper
  e. SweepResult — includes insufficient_data counter
  f. INSUFFICIENT_DATA label exists in SignalLabel enum
  g. classify_signal unchanged for existing labels
"""
from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


# ── a. Weighted median ─────────────────────────────────────────────────────────

class TestWeightedMedian(unittest.TestCase):
    def _wm(self, pairs):
        from backend.app.services.signal_service import _weighted_median
        return _weighted_median(pairs)

    def test_single_element(self):
        self.assertEqual(self._wm([(Decimal("10"), 1.0)]), Decimal("10"))

    def test_equal_weights_odd(self):
        # Sorted: 1, 5, 9 → median at cumulative ≥ 1.5 → 5
        result = self._wm([(Decimal("5"), 1.0), (Decimal("1"), 1.0), (Decimal("9"), 1.0)])
        self.assertEqual(result, Decimal("5"))

    def test_equal_weights_even(self):
        # Sorted: 1, 3, 5, 9 — total=4, half=2.0; cumulative hits 2.0 at element 3 → returns 3
        result = self._wm([(Decimal("1"), 1.0), (Decimal("3"), 1.0), (Decimal("5"), 1.0), (Decimal("9"), 1.0)])
        self.assertEqual(result, Decimal("3"))

    def test_higher_weight_pulls_median(self):
        # Low price with 2x weight should dominate
        result = self._wm([(Decimal("1"), 2.0), (Decimal("100"), 1.0)])
        self.assertEqual(result, Decimal("1"))

    def test_empty_raises(self):
        from backend.app.services.signal_service import _weighted_median
        with self.assertRaises(ValueError):
            _weighted_median([])

    def test_equal_weights_two_elements_lower_wins(self):
        # Sorted: 10, 20 — total=2, half=1.0; first element cumulative=1.0 ≥ 1.0
        result = self._wm([(Decimal("10"), 1.0), (Decimal("20"), 1.0)])
        self.assertEqual(result, Decimal("10"))


# ── b. Source weight parsing ───────────────────────────────────────────────────

class TestParseSourceWeights(unittest.TestCase):
    def _parse(self, s):
        from backend.app.services.signal_service import _parse_source_weights
        return _parse_source_weights(s)

    def test_basic_parse(self):
        result = self._parse("ebay_sold=2.0,pokemon_tcg_api=1.0")
        self.assertAlmostEqual(result["ebay_sold"], 2.0)
        self.assertAlmostEqual(result["pokemon_tcg_api"], 1.0)

    def test_single_weight(self):
        result = self._parse("pokemon_tcg_api=1.5")
        self.assertAlmostEqual(result["pokemon_tcg_api"], 1.5)

    def test_malformed_entry_skipped(self):
        result = self._parse("ebay_sold=2.0,badentry,pokemon_tcg_api=1.0")
        self.assertIn("ebay_sold", result)
        self.assertIn("pokemon_tcg_api", result)
        self.assertNotIn("badentry", result)

    def test_empty_string(self):
        result = self._parse("")
        self.assertEqual(result, {})


# ── c. _compute_delta_batch ────────────────────────────────────────────────────

class TestComputeDeltaBatch(unittest.TestCase):
    """Uses a mock DB session to test the batch delta computation.

    The new implementation issues two separate DB queries (baseline + current),
    so we mock execute() to return different results on successive calls.
    """

    def _make_baseline_row(self, asset_id, price, source):
        return SimpleNamespace(asset_id=asset_id, price=str(price), source=source)

    def _make_current_row(self, asset_id, price, source):
        return SimpleNamespace(asset_id=asset_id, price=str(price), source=source)

    def _make_db(self, baseline_rows, current_rows):
        """DB mock that returns baseline_rows on first execute, current_rows on second."""
        db = MagicMock()
        r1, r2 = MagicMock(), MagicMock()
        r1.all.return_value = baseline_rows
        r2.all.return_value = current_rows
        db.execute.side_effect = [r1, r2]
        return db

    def _call(self, db, asset_ids, now=None):
        from backend.app.services.signal_service import _compute_delta_batch
        if now is None:
            now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=UTC)
        return _compute_delta_batch(
            db,
            asset_ids,
            baseline_window_days=7,
            current_window_hours=24,
            source_weights={"pokemon_tcg_api": 1.0, "ebay_sold": 2.0},
            now=now,
        )

    def test_no_rows_returns_none(self):
        asset_id = "asset-1"
        db = self._make_db([], [])
        result = self._call(db, [asset_id])
        delta, ctx = result[asset_id]
        self.assertIsNone(delta)
        self.assertIn("reason", ctx)

    def test_only_current_no_baseline_returns_none(self):
        asset_id = "asset-1"
        db = self._make_db(
            [],  # no baseline
            [self._make_current_row(asset_id, "100.00", "pokemon_tcg_api")],
        )
        result = self._call(db, [asset_id])
        delta, ctx = result[asset_id]
        self.assertIsNone(delta)
        self.assertEqual(ctx["reason"], "no_baseline_data")

    def test_positive_delta(self):
        asset_id = "asset-1"
        db = self._make_db(
            [self._make_baseline_row(asset_id, "100.00", "pokemon_tcg_api")],
            [self._make_current_row(asset_id, "110.00", "pokemon_tcg_api")],
        )
        result = self._call(db, [asset_id])
        delta, ctx = result[asset_id]
        self.assertIsNotNone(delta)
        self.assertEqual(delta, Decimal("10.00"))

    def test_negative_delta(self):
        asset_id = "asset-1"
        db = self._make_db(
            [self._make_baseline_row(asset_id, "100.00", "pokemon_tcg_api")],
            [self._make_current_row(asset_id, "80.00", "pokemon_tcg_api")],
        )
        result = self._call(db, [asset_id])
        delta, ctx = result[asset_id]
        self.assertIsNotNone(delta)
        self.assertEqual(delta, Decimal("-20.00"))

    def test_zero_baseline_returns_none(self):
        asset_id = "asset-1"
        db = self._make_db(
            [self._make_baseline_row(asset_id, "0.00", "pokemon_tcg_api")],
            [self._make_current_row(asset_id, "10.00", "pokemon_tcg_api")],
        )
        result = self._call(db, [asset_id])
        delta, ctx = result[asset_id]
        self.assertIsNone(delta)
        self.assertEqual(ctx["reason"], "zero_baseline")

    def test_higher_weight_source_dominates(self):
        """ebay_sold (weight=2) should dominate over pokemon_tcg_api (weight=1)."""
        asset_id = "asset-1"
        db = self._make_db(
            # Baseline: ebay=100 (w=2), tcg=150 (w=1) → weighted median = 100
            [
                self._make_baseline_row(asset_id, "100.00", "ebay_sold"),
                self._make_baseline_row(asset_id, "150.00", "pokemon_tcg_api"),
            ],
            # Current: ebay=110 (w=2), tcg=160 (w=1) → weighted median = 110
            [
                self._make_current_row(asset_id, "110.00", "ebay_sold"),
                self._make_current_row(asset_id, "160.00", "pokemon_tcg_api"),
            ],
        )
        result = self._call(db, [asset_id])
        delta, ctx = result[asset_id]
        self.assertIsNotNone(delta)
        self.assertEqual(delta, Decimal("10.00"))

    def test_multiple_assets_independent(self):
        a1, a2 = "asset-1", "asset-2"
        db = self._make_db(
            [
                self._make_baseline_row(a1, "100.00", "pokemon_tcg_api"),
                self._make_baseline_row(a2, "50.00", "pokemon_tcg_api"),
            ],
            [
                self._make_current_row(a1, "120.00", "pokemon_tcg_api"),
                self._make_current_row(a2, "50.00", "pokemon_tcg_api"),
            ],
        )
        result = self._call(db, [a1, a2])
        d1, _ = result[a1]
        d2, _ = result[a2]
        self.assertEqual(d1, Decimal("20.00"))
        self.assertEqual(d2, Decimal("0.00"))

    def test_context_contains_expected_keys(self):
        asset_id = "asset-1"
        db = self._make_db(
            [self._make_baseline_row(asset_id, "100.00", "pokemon_tcg_api")],
            [self._make_current_row(asset_id, "105.00", "pokemon_tcg_api")],
        )
        result = self._call(db, [asset_id])
        delta, ctx = result[asset_id]
        self.assertIn("baseline_n", ctx)
        self.assertIn("current_n", ctx)
        self.assertIn("baseline_price", ctx)
        self.assertIn("current_price", ctx)
        self.assertIn("delta_pct", ctx)


# ── d. compute_signal_delta (single-asset wrapper) ────────────────────────────

class TestComputeSignalDelta(unittest.TestCase):
    def test_delegates_to_batch(self):
        from backend.app.services.signal_service import compute_signal_delta
        now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=UTC)
        with patch("backend.app.services.signal_service._compute_delta_batch") as mock_batch:
            mock_batch.return_value = {"asset-1": (Decimal("5.00"), {"delta_pct": 5.0})}
            db = MagicMock()
            delta, ctx = compute_signal_delta(db, "asset-1", now=now)
            self.assertEqual(delta, Decimal("5.00"))
            mock_batch.assert_called_once()

    def test_missing_asset_returns_none(self):
        from backend.app.services.signal_service import compute_signal_delta
        now = datetime(2026, 4, 19, 12, 0, 0, tzinfo=UTC)
        with patch("backend.app.services.signal_service._compute_delta_batch") as mock_batch:
            mock_batch.return_value = {}
            db = MagicMock()
            delta, ctx = compute_signal_delta(db, "asset-99", now=now)
            self.assertIsNone(delta)
            self.assertIn("reason", ctx)


# ── e. SweepResult includes insufficient_data ──────────────────────────────────

class TestSweepResult(unittest.TestCase):
    def test_has_insufficient_data_field(self):
        from backend.app.services.signal_service import SweepResult
        r = SweepResult()
        self.assertEqual(r.insufficient_data, 0)

    def test_all_fields_present(self):
        from backend.app.services.signal_service import SweepResult
        r = SweepResult(total=10, breakout=1, move=2, watch=3, idle=2, insufficient_data=2, errors=0)
        self.assertEqual(r.total, 10)
        self.assertEqual(r.insufficient_data, 2)


# ── f. INSUFFICIENT_DATA enum value ───────────────────────────────────────────

class TestSignalLabelEnum(unittest.TestCase):
    def test_insufficient_data_exists(self):
        from backend.app.models.enums import SignalLabel
        self.assertEqual(SignalLabel.INSUFFICIENT_DATA.value, "INSUFFICIENT_DATA")

    def test_all_original_labels_still_exist(self):
        from backend.app.models.enums import SignalLabel
        for label in ("BREAKOUT", "MOVE", "WATCH", "IDLE"):
            self.assertIn(label, SignalLabel._value2member_map_)


# ── g. classify_signal unchanged for existing labels ──────────────────────────

class TestClassifySignalUnchanged(unittest.TestCase):
    def _classify(self, **kwargs):
        from backend.app.services.signal_service import classify_signal
        return classify_signal(**kwargs)

    def test_breakout(self):
        from backend.app.models.enums import SignalLabel
        result = self._classify(
            alert_confidence=75,
            price_delta_pct=Decimal("12.0"),
            liquidity_score=65,
            prediction="Up",
            history_depth=5,
        )
        self.assertEqual(result, SignalLabel.BREAKOUT)

    def test_move(self):
        from backend.app.models.enums import SignalLabel
        result = self._classify(
            alert_confidence=50,
            price_delta_pct=Decimal("6.0"),
            liquidity_score=40,
            prediction=None,
            history_depth=2,
        )
        self.assertEqual(result, SignalLabel.MOVE)

    def test_watch(self):
        # WATCH requires price_delta_pct >= 0 (cd64b4f: falling cards are never WATCH).
        # Use 2.0% — below MOVE_DELTA_MIN (5%) but non-negative.
        from backend.app.models.enums import SignalLabel
        result = self._classify(
            alert_confidence=None,
            price_delta_pct=Decimal("2.0"),
            liquidity_score=30,
            prediction="Up",
            history_depth=4,
        )
        self.assertEqual(result, SignalLabel.WATCH)

    def test_idle(self):
        from backend.app.models.enums import SignalLabel
        result = self._classify(
            alert_confidence=None,
            price_delta_pct=None,
            liquidity_score=10,
            prediction=None,
            history_depth=1,
        )
        self.assertEqual(result, SignalLabel.IDLE)


# ── h. Downgrade rules (_apply_signal_downgrade) ──────────────────────────────

class TestApplySignalDowngrade(unittest.TestCase):
    """Tests for the chained price-floor + baseline-n downgrade rules.

    Defaults from config:
      signal_breakout_min_price_usd = 2.00
      signal_move_min_price_usd     = 1.00
      signal_breakout_min_baseline_n = 3
      signal_move_min_baseline_n     = 2
    """

    def _downgrade(self, candidate, price, baseline_n, baseline_price="1.00"):
        from backend.app.services.signal_service import _apply_signal_downgrade
        from backend.app.models.enums import SignalLabel
        return _apply_signal_downgrade(
            candidate,
            current_price=Decimal(str(price)),
            baseline_price=Decimal(str(baseline_price)),
            baseline_n=baseline_n,
        )

    def test_breakout_low_price_downgrades_to_move(self):
        from backend.app.models.enums import SignalLabel
        label, reason = self._downgrade(SignalLabel.BREAKOUT, price=0.50, baseline_n=5)
        self.assertEqual(label, SignalLabel.MOVE)
        self.assertEqual(reason, "low_absolute_price")

    def test_breakout_insufficient_n1_hard_floor_in_process_batch(self):
        # baseline_n=1 is caught by the hard-floor BEFORE classify_signal runs;
        # so downgrade function receives a candidate of BREAKOUT with n=1 only if
        # baseline_n >= move_min_baseline_n (2).  With n=1, _process_batch returns
        # INSUFFICIENT_DATA before calling this function at all.
        # This test verifies the downgrade function itself: n=2 is still <
        # breakout_min_baseline_n (3), so BREAKOUT → MOVE.
        from backend.app.models.enums import SignalLabel
        label, reason = self._downgrade(SignalLabel.BREAKOUT, price=5.00, baseline_n=2)
        self.assertEqual(label, SignalLabel.MOVE)
        self.assertEqual(reason, "insufficient_baseline_n")

    def test_breakout_sufficient_conditions_no_downgrade(self):
        # price >= 2.00, baseline_n >= 3 → stays BREAKOUT
        from backend.app.models.enums import SignalLabel
        label, reason = self._downgrade(SignalLabel.BREAKOUT, price=5.00, baseline_n=3)
        self.assertEqual(label, SignalLabel.BREAKOUT)
        self.assertIsNone(reason)

    def test_move_low_price_downgrades_to_watch(self):
        from backend.app.models.enums import SignalLabel
        label, reason = self._downgrade(SignalLabel.MOVE, price=0.50, baseline_n=5)
        self.assertEqual(label, SignalLabel.WATCH)
        self.assertEqual(reason, "low_absolute_price")

    def test_move_price_at_threshold_no_downgrade(self):
        # price == signal_move_min_price_usd (1.00) → not < threshold → no downgrade
        from backend.app.models.enums import SignalLabel
        label, reason = self._downgrade(SignalLabel.MOVE, price=1.00, baseline_n=5)
        self.assertEqual(label, SignalLabel.MOVE)
        self.assertIsNone(reason)

    def test_move_price_above_threshold_no_downgrade(self):
        from backend.app.models.enums import SignalLabel
        label, reason = self._downgrade(SignalLabel.MOVE, price=1.50, baseline_n=5)
        self.assertEqual(label, SignalLabel.MOVE)
        self.assertIsNone(reason)

    def test_watch_never_downgraded(self):
        # WATCH is not subject to price-floor rules
        from backend.app.models.enums import SignalLabel
        label, reason = self._downgrade(SignalLabel.WATCH, price=0.01, baseline_n=5)
        self.assertEqual(label, SignalLabel.WATCH)
        self.assertIsNone(reason)

    def test_idle_never_downgraded(self):
        from backend.app.models.enums import SignalLabel
        label, reason = self._downgrade(SignalLabel.IDLE, price=0.01, baseline_n=5)
        self.assertEqual(label, SignalLabel.IDLE)
        self.assertIsNone(reason)

    def test_breakout_exact_min_price_no_downgrade(self):
        # price == signal_breakout_min_price_usd (2.00), n >= 3 → no downgrade
        from backend.app.models.enums import SignalLabel
        label, reason = self._downgrade(SignalLabel.BREAKOUT, price=2.00, baseline_n=3)
        self.assertEqual(label, SignalLabel.BREAKOUT)
        self.assertIsNone(reason)

    def test_breakout_price_priority_over_baseline_n(self):
        # price < breakout_min triggers first (low_absolute_price), not baseline_n check
        from backend.app.models.enums import SignalLabel
        label, reason = self._downgrade(SignalLabel.BREAKOUT, price=0.50, baseline_n=2)
        self.assertEqual(label, SignalLabel.MOVE)
        self.assertEqual(reason, "low_absolute_price")


if __name__ == "__main__":
    unittest.main()
