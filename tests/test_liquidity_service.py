from __future__ import annotations

from unittest import TestCase

from backend.app.services.liquidity_service import (
    HIGH_CONFIDENCE_LABEL,
    HIGH_LIQUIDITY_LABEL,
    LOW_CONFIDENCE_LABEL,
    LOW_LIQUIDITY_LABEL,
    compute_alert_confidence,
    compute_liquidity_score,
    classify_alert_confidence_label,
    classify_liquidity_label,
)


class LiquidityServiceTests(TestCase):
    def test_liquidity_score_is_zero_when_no_real_history_exists(self):
        score = compute_liquidity_score(
            sales_count_7d=0,
            sales_count_30d=0,
            days_since_last_sale=None,
            history_depth=0,
            source_count=0,
        )

        self.assertEqual(score, 0)
        self.assertEqual(classify_liquidity_label(score), LOW_LIQUIDITY_LABEL)

    def test_liquidity_score_stays_low_for_shallow_history(self):
        score = compute_liquidity_score(
            sales_count_7d=1,
            sales_count_30d=2,
            days_since_last_sale=10,
            history_depth=2,
            source_count=1,
        )

        self.assertEqual(score, 32)
        self.assertEqual(classify_liquidity_label(score), LOW_LIQUIDITY_LABEL)

    def test_liquidity_score_is_high_for_active_recent_history(self):
        score = compute_liquidity_score(
            sales_count_7d=8,
            sales_count_30d=12,
            days_since_last_sale=1,
            history_depth=14,
            source_count=2,
        )

        self.assertEqual(score, 98)
        self.assertEqual(classify_liquidity_label(score), HIGH_LIQUIDITY_LABEL)

    def test_alert_confidence_is_high_for_strong_move_with_strong_liquidity(self):
        score = compute_alert_confidence(
            price_move_magnitude=12,
            liquidity_score=98,
            source_agreement=85,
            outlier_handling=90,
        )

        self.assertEqual(score, 91)
        self.assertEqual(classify_alert_confidence_label(score), HIGH_CONFIDENCE_LABEL)

    def test_alert_confidence_stays_low_for_strong_move_with_weak_liquidity(self):
        score = compute_alert_confidence(
            price_move_magnitude=12,
            liquidity_score=20,
            source_agreement=50,
            outlier_handling=30,
        )

        self.assertEqual(score, 44)
        self.assertEqual(classify_alert_confidence_label(score), LOW_CONFIDENCE_LABEL)
