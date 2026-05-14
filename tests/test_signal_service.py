"""Unit tests for signal_service helpers that are not CardMarket-pipeline-specific."""
from decimal import Decimal

import pytest

from backend.app.models.enums import SignalLabel
from backend.app.services.signal_service import (
    CARDMARKET_EUR_TO_USD,
    _apply_signal_downgrade,
    _eur_to_usd,
)


def test_cardmarket_thresholds_use_eur_to_usd_conversion():
    """EUR current_price of €1.95 × 1.09 = $2.1255, which clears the
    signal_breakout_min_price_usd=$2.00 gate. Without conversion the same
    value (1.95 < 2.00) would be incorrectly downgraded to MOVE.
    """
    eur_price = Decimal("1.95")

    # Without conversion: €1.95 < $2.00 threshold → downgraded to MOVE
    label_raw, reason_raw = _apply_signal_downgrade(
        SignalLabel.BREAKOUT,
        current_price=eur_price,
        baseline_price=Decimal("3.00"),
        baseline_n=5,
    )
    assert reason_raw == "low_absolute_price"
    assert label_raw == SignalLabel.MOVE

    # With EUR→USD conversion: $2.1255 > $2.00 → no downgrade
    usd_equiv = _eur_to_usd(eur_price)
    label_converted, reason_converted = _apply_signal_downgrade(
        SignalLabel.BREAKOUT,
        current_price=usd_equiv,
        baseline_price=Decimal("3.00"),
        baseline_n=5,
    )
    assert reason_converted is None
    assert label_converted == SignalLabel.BREAKOUT


def test_eur_to_usd_uses_provisonal_rate():
    assert _eur_to_usd(Decimal("1.00")) == CARDMARKET_EUR_TO_USD


def test_eur_to_usd_boundary_above_move_floor():
    """€0.95 * 1.09 = $1.0355 — clears the $1.00 MOVE floor."""
    assert _eur_to_usd(Decimal("0.95")) > Decimal("1.00")


def test_eur_to_usd_boundary_below_bulk_floor():
    """€0.45 * 1.09 = $0.4905 — still below $0.50 bulk floor (correctly suppressed)."""
    assert _eur_to_usd(Decimal("0.45")) < Decimal("0.50")
