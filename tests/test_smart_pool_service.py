from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from backend.app.services.smart_pool_service import get_smart_pool_candidates


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, _stmt):
        return FakeResult(self.rows)


class SmartPoolServiceTests(TestCase):
    @patch("backend.app.services.smart_pool_service.get_active_price_source_filter", return_value=True)
    def test_returns_empty_when_no_history(self, _get_active_price_source_filter_mock):
        db = FakeSession([])

        result = get_smart_pool_candidates(db)

        self.assertEqual(result, [])

    @patch("backend.app.services.smart_pool_service.get_active_price_source_filter", return_value=True)
    def test_returns_candidates_ranked_by_change_count(self, _get_active_price_source_filter_mock):
        first_asset_id = uuid.uuid4()
        second_asset_id = uuid.uuid4()
        db = FakeSession(
            [
                SimpleNamespace(
                    id=first_asset_id,
                    name="Umbreon ex",
                    set_name="Prismatic Evolutions",
                    change_count=5,
                    min_price=Decimal("100.00"),
                    max_price=Decimal("125.00"),
                    latest_price=Decimal("125.00"),
                ),
                SimpleNamespace(
                    id=second_asset_id,
                    name="Pikachu ex",
                    set_name="Surging Sparks",
                    change_count=2,
                    min_price=Decimal("50.00"),
                    max_price=Decimal("55.00"),
                    latest_price=Decimal("55.00"),
                ),
            ]
        )

        result = get_smart_pool_candidates(db)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].asset_id, first_asset_id)
        self.assertEqual(result[0].price_change_count_7d, 5)

    @patch("backend.app.services.smart_pool_service.get_active_price_source_filter", return_value=True)
    def test_price_range_pct_calculated_correctly(self, _get_active_price_source_filter_mock):
        db = FakeSession(
            [
                SimpleNamespace(
                    id=uuid.uuid4(),
                    name="Charizard",
                    set_name="Base Set",
                    change_count=3,
                    min_price=Decimal("100.00"),
                    max_price=Decimal("120.00"),
                    latest_price=Decimal("120.00"),
                )
            ]
        )

        result = get_smart_pool_candidates(db)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].price_range_pct, Decimal("20.00"))
