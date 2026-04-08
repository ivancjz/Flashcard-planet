from __future__ import annotations

from unittest import TestCase
from unittest.mock import Mock

from backend.app.core.price_sources import SAMPLE_PRICE_SOURCE
from webui import _load_chart_data


class WebUiChartTests(TestCase):
    def test_returns_empty_list_when_no_real_history(self):
        session = Mock()
        session.execute.return_value.all.return_value = []

        result = _load_chart_data(session, "asset-1")

        self.assertEqual(result, [])

    def test_excludes_sample_seed_rows(self):
        session = Mock()
        session.execute.return_value.all.return_value = [
            type(
                "Row",
                (),
                {
                    "captured_at": None,
                    "price": "10.00",
                    "source": SAMPLE_PRICE_SOURCE,
                },
            )()
        ]

        result = _load_chart_data(session, "asset-1")

        self.assertEqual(result, [])
