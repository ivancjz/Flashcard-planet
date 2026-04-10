"""Tests for signal history model and sweep append behaviour."""
from __future__ import annotations

import unittest

from backend.app.models.asset_signal_history import AssetSignalHistory


def test_asset_signal_history_model_fields():
    """AssetSignalHistory must have all required fields."""
    import uuid
    from datetime import UTC, datetime
    from decimal import Decimal

    h = AssetSignalHistory(
        asset_id=uuid.uuid4(),
        label="BREAKOUT",
        confidence=75,
        price_delta_pct=Decimal("12.50"),
        liquidity_score=80,
        prediction="Up",
        computed_at=datetime.now(UTC),
    )
    assert h.label == "BREAKOUT"
    assert h.confidence == 75


def test_append_history_is_callable():
    from backend.app.services.signal_service import _append_history

    assert callable(_append_history)


def test_get_daily_snapshot_signals_is_callable():
    from backend.app.services.signal_service import get_daily_snapshot_signals

    assert callable(get_daily_snapshot_signals)


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            suite.addTest(unittest.FunctionTestCase(value))
    return suite
