from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from backend.app.services.liquidity_service import AssetSignalSnapshot
from backend.app.services.price_service import get_asset_history_by_name, get_top_movers


class PriceServiceTests(TestCase):
    @patch("backend.app.services.price_service.get_asset_signal_snapshots")
    @patch("backend.app.services.price_service.get_active_price_source_filter")
    def test_top_movers_excludes_illiquid_assets(
        self,
        get_active_price_source_filter_mock,
        get_asset_signal_snapshots_mock,
    ):
        asset_a = uuid.uuid4()
        asset_b = uuid.uuid4()
        db = Mock()
        db.execute.return_value.all.return_value = [
            SimpleNamespace(
                id=asset_a,
                name="Umbreon ex",
                category="Pokemon",
                latest_price=Decimal("120.00"),
                previous_price=Decimal("100.00"),
            ),
            SimpleNamespace(
                id=asset_b,
                name="Thin Card",
                category="Pokemon",
                latest_price=Decimal("24.00"),
                previous_price=Decimal("20.00"),
            ),
        ]
        get_active_price_source_filter_mock.return_value = True
        get_asset_signal_snapshots_mock.return_value = {
            asset_a: AssetSignalSnapshot(
                asset_id=asset_a,
                sales_count_7d=4,
                sales_count_30d=8,
                days_since_last_sale=1,
                last_real_sale_at=datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
                history_depth=12,
                source_count=1,
                liquidity_score=80,
                liquidity_label="High Liquidity",
                price_move_magnitude=Decimal("20.00"),
                alert_confidence=76,
                alert_confidence_label="High Confidence",
            ),
            asset_b: AssetSignalSnapshot(
                asset_id=asset_b,
                sales_count_7d=1,
                sales_count_30d=2,
                days_since_last_sale=20,
                last_real_sale_at=datetime(2026, 3, 10, 10, 0, tzinfo=UTC),
                history_depth=4,
                source_count=1,
                liquidity_score=28,
                liquidity_label="Low Liquidity",
                price_move_magnitude=Decimal("20.00"),
                alert_confidence=33,
                alert_confidence_label="Low Confidence",
            ),
        }

        movers = get_top_movers(db, limit=10)

        self.assertEqual(len(movers), 1)
        self.assertEqual(movers[0].name, "Umbreon ex")
        self.assertEqual(movers[0].liquidity_score, 80)
        self.assertEqual(movers[0].alert_confidence, 76)
        self.assertEqual(movers[0].sales_count_30d, 8)
        self.assertEqual(movers[0].days_since_last_sale, 1)

    @patch("backend.app.services.price_service.get_asset_prices_by_name")
    @patch("backend.app.services.price_service.get_active_price_source_filter")
    def test_asset_history_marks_points_as_derived_and_real(
        self,
        get_active_price_source_filter_mock,
        get_asset_prices_by_name_mock,
    ):
        asset_id = uuid.uuid4()
        db = Mock()
        get_active_price_source_filter_mock.return_value = True
        get_asset_prices_by_name_mock.return_value = [
            SimpleNamespace(
                asset_id=asset_id,
                name="Bulbasaur",
                category="Pokemon",
                set_name="Scarlet & Violet 151",
                latest_price=Decimal("0.20"),
                currency="USD",
                liquidity_score=72,
                liquidity_label="Medium Liquidity",
                last_real_sale_at=datetime(2026, 4, 2, 14, 31, tzinfo=UTC),
                days_since_last_sale=0,
                sales_count_7d=5,
                sales_count_30d=7,
                history_depth=9,
                source_count=1,
                alert_confidence=68,
                alert_confidence_label="Medium Confidence",
            )
        ]
        db.execute.return_value.all.return_value = [
            SimpleNamespace(
                captured_at=datetime(2026, 4, 2, 14, 31, tzinfo=UTC),
                price=Decimal("0.20"),
                currency="USD",
                source="pokemon_tcg_api",
            ),
            SimpleNamespace(
                captured_at=datetime(2026, 4, 2, 14, 26, tzinfo=UTC),
                price=Decimal("0.18"),
                currency="USD",
                source="pokemon_tcg_api",
            ),
        ]

        history = get_asset_history_by_name(db, "Bulbasaur", limit=5)

        self.assertIsNotNone(history)
        self.assertEqual(history.liquidity_score, 72)
        self.assertEqual(history.alert_confidence, 68)
        self.assertEqual(history.history[0].point_type, "derived")
        self.assertEqual(history.history[0].event_type, "derived")
        self.assertTrue(history.history[0].is_real_data)
        self.assertEqual(history.history[0].timestamp, history.history[0].captured_at)
