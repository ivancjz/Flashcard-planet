"""Unit tests for driver_attribution_service.py

Uses unittest.mock throughout — no DB connection required.
Tests attribute_signal priority ordering + pure helper functions.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import backend.app.services.driver_attribution_service as _das
from backend.app.services.driver_attribution_service import (
    SUPPLY_LOOKBACK_EXTENSION_DAYS,
    UNKNOWN_CONFIDENCE,
    _EVENT_TYPE_CONFIDENCE_WEIGHT,
    _recency_score,
    attribute_signal,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _asset(set_name: str = "Chaos Rising") -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), set_name=set_name, game="pokemon")


def _event(
    *,
    event_type: str = "INFLUENCER",
    days_ago: int = 3,
    expected_window_days: int = 14,
    description: str = "test event",
    set_name: str | None = None,
    asset: SimpleNamespace | None = None,
) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        event_date=now - timedelta(days=days_ago),
        event_type=event_type,
        description=description,
        expected_window_days=expected_window_days,
        affected_asset_ids=[str(asset.id)] if asset else [],
        affected_set_ids=[set_name] if set_name else [],
    )


def _db_returning(asset: SimpleNamespace) -> MagicMock:
    db = MagicMock()
    db.get.return_value = asset
    return db


# ── _recency_score (pure function) ────────────────────────────────────────────

def test_recency_score_just_happened():
    now = datetime.now(UTC)
    score = _recency_score(now - timedelta(hours=1), now, 14)
    assert score > 0.99


def test_recency_score_at_window_end():
    now = datetime.now(UTC)
    score = _recency_score(now - timedelta(days=14), now, 14)
    assert score == pytest.approx(0.0, abs=0.02)


def test_recency_score_midpoint():
    now = datetime.now(UTC)
    score = _recency_score(now - timedelta(days=7), now, 14)
    assert 0.45 < score < 0.55


def test_recency_score_past_window_is_zero():
    now = datetime.now(UTC)
    score = _recency_score(now - timedelta(days=20), now, 14)
    assert score == 0.0


def test_recency_score_none_window_defaults_to_14():
    now = datetime.now(UTC)
    s_none = _recency_score(now - timedelta(days=7), now, None)
    s_14 = _recency_score(now - timedelta(days=7), now, 14)
    assert s_none == pytest.approx(s_14)


# ── attribute_signal: UNKNOWN default ────────────────────────────────────────

def test_unknown_when_asset_not_found():
    db = MagicMock()
    db.get.return_value = None
    result = attribute_signal(db, asset_id=uuid.uuid4(), signal_move_pct=Decimal("10"), signal_window_days=7)
    assert result.driver == "UNKNOWN"
    assert "not found" in result.reason


def test_unknown_when_no_events_no_breadth():
    a = _asset()
    db = _db_returning(a)
    with (
        patch.object(_das, "_matching_events", return_value=[]),
        patch.object(_das, "_check_macro_breadth", return_value=None),
    ):
        result = attribute_signal(db, asset_id=a.id, signal_move_pct=Decimal("5"), signal_window_days=7)
    assert result.driver == "UNKNOWN"
    assert result.confidence == UNKNOWN_CONFIDENCE


# ── attribute_signal: EVENT_DRIVEN (INFLUENCER) ───────────────────────────────

def test_event_driven_influencer_recent():
    a = _asset()
    db = _db_returning(a)
    ev = _event(event_type="INFLUENCER", days_ago=1, set_name="Chaos Rising")

    with (
        patch.object(_das, "_matching_events", return_value=[ev]),
        patch.object(_das, "_check_macro_breadth", return_value=None),
    ):
        result = attribute_signal(db, asset_id=a.id, signal_move_pct=Decimal("20"), signal_window_days=7)

    assert result.driver == "EVENT_DRIVEN"
    assert result.event_id == ev.id
    assert result.event_type == "INFLUENCER"
    assert result.confidence > 0.5


def test_event_driven_influencer_confidence_decays_with_age():
    a1, a2 = _asset(), _asset()

    ev_recent = _event(event_type="INFLUENCER", days_ago=1)
    ev_old = _event(event_type="INFLUENCER", days_ago=12)

    with patch.object(_das, "_matching_events", return_value=[ev_recent]):
        r1 = attribute_signal(_db_returning(a1), asset_id=a1.id, signal_move_pct=Decimal("10"), signal_window_days=14)
    with patch.object(_das, "_matching_events", return_value=[ev_old]):
        r2 = attribute_signal(_db_returning(a2), asset_id=a2.id, signal_move_pct=Decimal("10"), signal_window_days=14)

    assert r1.driver == r2.driver == "EVENT_DRIVEN"
    assert r1.confidence > r2.confidence


def test_event_driven_picks_most_recent_event():
    """If multiple events match, the most recent should be picked."""
    a = _asset()
    db = _db_returning(a)
    ev_recent = _event(event_type="INFLUENCER", days_ago=1, description="recent")
    ev_old = _event(event_type="INFLUENCER", days_ago=5, description="old")

    with patch.object(_das, "_matching_events", return_value=[ev_old, ev_recent]):
        result = attribute_signal(db, asset_id=a.id, signal_move_pct=Decimal("10"), signal_window_days=7)

    assert result.driver == "EVENT_DRIVEN"
    assert result.event_description == "recent"


def test_event_driven_tournament():
    a = _asset()
    db = _db_returning(a)
    ev = _event(event_type="TOURNAMENT", days_ago=3, set_name="Journey Together")

    with patch.object(_das, "_matching_events", return_value=[ev]):
        result = attribute_signal(db, asset_id=a.id, signal_move_pct=Decimal("8"), signal_window_days=7)

    assert result.driver == "EVENT_DRIVEN"
    assert result.event_type == "TOURNAMENT"
    assert result.confidence > 0


# ── attribute_signal: MACRO ───────────────────────────────────────────────────

def test_macro_when_breadth_exceeds_threshold():
    a = _asset()
    db = _db_returning(a)

    with (
        patch.object(_das, "_matching_events", return_value=[]),
        patch.object(_das, "_check_macro_breadth", return_value=0.80),
    ):
        result = attribute_signal(db, asset_id=a.id, signal_move_pct=Decimal("7"), signal_window_days=7)

    assert result.driver == "MACRO"
    assert result.confidence > 0.5


def test_macro_confidence_scales_with_breadth():
    a1, a2 = _asset(), _asset()

    with (
        patch.object(_das, "_matching_events", return_value=[]),
        patch.object(_das, "_check_macro_breadth", return_value=0.65),
    ):
        r_low = attribute_signal(_db_returning(a1), asset_id=a1.id, signal_move_pct=Decimal("5"), signal_window_days=7)

    with (
        patch.object(_das, "_matching_events", return_value=[]),
        patch.object(_das, "_check_macro_breadth", return_value=0.95),
    ):
        r_high = attribute_signal(_db_returning(a2), asset_id=a2.id, signal_move_pct=Decimal("5"), signal_window_days=7)

    assert r_high.confidence >= r_low.confidence


def test_macro_not_triggered_below_threshold():
    a = _asset()
    db = _db_returning(a)

    # Breadth 50% < 60% threshold
    with (
        patch.object(_das, "_matching_events", return_value=[]),
        patch.object(_das, "_check_macro_breadth", return_value=0.50),
    ):
        result = attribute_signal(db, asset_id=a.id, signal_move_pct=Decimal("5"), signal_window_days=7)

    assert result.driver != "MACRO"


def test_macro_corroborated_by_release_event():
    a = _asset(set_name="Chaos Rising")
    db = _db_returning(a)
    release_ev = _event(event_type="RELEASE", days_ago=5, set_name="Chaos Rising", description="Chaos Rising launch")

    calls = [
        [],              # EVENT_DRIVEN query (no INFLUENCER/TOURNAMENT)
        [release_ev],    # RELEASE query (MACRO corroboration)
    ]

    def _mock_matching(*args, **kwargs):
        return calls.pop(0)

    with (
        patch.object(_das, "_matching_events", side_effect=_mock_matching),
        patch.object(_das, "_check_macro_breadth", return_value=0.75),
    ):
        result = attribute_signal(db, asset_id=a.id, signal_move_pct=Decimal("10"), signal_window_days=7)

    assert result.driver == "MACRO"
    assert result.event_id == release_ev.id


# ── attribute_signal: SUPPLY_SHOCK ───────────────────────────────────────────

def test_supply_shock_from_supply_event():
    a = _asset()
    db = _db_returning(a)
    supply_ev = _event(event_type="SUPPLY", days_ago=10, set_name="Evolving Skies")

    # First two calls (EVENT_DRIVEN check) return empty, third call (SUPPLY) returns event
    calls = [[], supply_ev]

    def _mock_matching(*args, **kwargs):
        val = calls.pop(0)
        return val if isinstance(val, list) else [val]

    with (
        patch.object(_das, "_matching_events", side_effect=_mock_matching),
        patch.object(_das, "_check_macro_breadth", return_value=None),
    ):
        result = attribute_signal(db, asset_id=a.id, signal_move_pct=Decimal("-12"), signal_window_days=7)

    assert result.driver == "SUPPLY_SHOCK"
    assert result.confidence > 0


def test_supply_confidence_lower_than_influencer():
    """SUPPLY should yield lower confidence than a same-age INFLUENCER event."""
    a1, a2 = _asset(), _asset()

    ev = _event(days_ago=5)

    ev_influencer = SimpleNamespace(**vars(ev))
    ev_influencer.event_type = "INFLUENCER"

    ev_supply = SimpleNamespace(**vars(ev))
    ev_supply.event_type = "SUPPLY"

    with patch.object(_das, "_matching_events", return_value=[ev_influencer]):
        r_inf = attribute_signal(_db_returning(a1), asset_id=a1.id, signal_move_pct=Decimal("10"), signal_window_days=7)

    with (
        patch.object(_das, "_matching_events", side_effect=[[], [ev_supply]]),
        patch.object(_das, "_check_macro_breadth", return_value=None),
    ):
        r_sup = attribute_signal(_db_returning(a2), asset_id=a2.id, signal_move_pct=Decimal("10"), signal_window_days=7)

    assert r_inf.driver == "EVENT_DRIVEN"
    assert r_sup.driver == "SUPPLY_SHOCK"
    assert r_inf.confidence > r_sup.confidence


# ── attribute_signal: Rule 4 — card-specific RELEASE → EVENT_DRIVEN ──────────

def test_release_on_specific_card_triggers_event_driven():
    """A RELEASE event with asset_id in affected_asset_ids → EVENT_DRIVEN."""
    a = _asset(set_name="Chaos Rising")
    db = _db_returning(a)
    # Event has this card's UUID in affected_asset_ids
    release_ev = _event(event_type="RELEASE", days_ago=2, asset=a, description="Chaos Rising - Mega Greninja ex SIR")

    def _mock_matching(*args, **kwargs):
        return [release_ev]

    with (
        patch.object(_das, "_matching_events", side_effect=_mock_matching),
        patch.object(_das, "_check_macro_breadth", return_value=None),
    ):
        result = attribute_signal(db, asset_id=a.id, signal_move_pct=Decimal("18"), signal_window_days=7)

    assert result.driver == "EVENT_DRIVEN"
    assert result.event_type == "RELEASE"
    assert result.confidence > 0


def test_release_set_wide_only_does_not_trigger_rule4():
    """A RELEASE event with only set_name match (no asset_id) does NOT trigger Rule 4."""
    a = _asset(set_name="Chaos Rising")
    db = _db_returning(a)
    # Event touches set-wide only; affected_asset_ids is empty
    release_ev = _event(event_type="RELEASE", days_ago=2, set_name="Chaos Rising")
    assert release_ev.affected_asset_ids == []

    # Use side_effect so each call gets appropriate events per event_types filter
    def _side_effect(*args, **kwargs):
        event_types = kwargs.get("event_types") or []
        if set(event_types) & {"INFLUENCER", "TOURNAMENT"}:
            return []   # Rule 1: no hype events
        if set(event_types) & {"SUPPLY"}:
            return []   # Rule 3: no supply events
        if set(event_types) & {"RELEASE"}:
            return [release_ev]  # Rule 2 & 4: set-wide release found
        return []

    with (
        patch.object(_das, "_matching_events", side_effect=_side_effect),
        patch.object(_das, "_check_macro_breadth", return_value=None),
    ):
        result = attribute_signal(db, asset_id=a.id, signal_move_pct=Decimal("10"), signal_window_days=7)

    # affected_asset_ids=[] → card_specific_releases=[] → Rule 4 doesn't fire → UNKNOWN
    assert result.driver == "UNKNOWN"


def test_release_confidence_uses_updated_weight():
    """RELEASE event_type_weight is 0.75 (not 0.55), giving meaningful confidence."""
    a = _asset(set_name="Chaos Rising")
    db = _db_returning(a)
    # Very recent release (recency ≈ 1.0) → confidence ≈ 0.75
    release_ev = _event(event_type="RELEASE", days_ago=0, asset=a)

    with patch.object(_das, "_matching_events", return_value=[release_ev]):
        result = attribute_signal(db, asset_id=a.id, signal_move_pct=Decimal("20"), signal_window_days=7)

    assert result.driver == "EVENT_DRIVEN"
    assert result.confidence >= 0.70  # recency≈1.0 × weight=0.75


# ── priority ordering ─────────────────────────────────────────────────────────

def test_event_driven_beats_macro():
    """EVENT_DRIVEN rule fires first, MACRO check is never reached."""
    a = _asset()
    db = _db_returning(a)
    ev = _event(event_type="INFLUENCER", days_ago=1)

    mock_breadth = MagicMock(return_value=0.9)  # would trigger MACRO if reached

    with (
        patch.object(_das, "_matching_events", return_value=[ev]),
        patch.object(_das, "_check_macro_breadth", mock_breadth),
    ):
        result = attribute_signal(db, asset_id=a.id, signal_move_pct=Decimal("20"), signal_window_days=7)

    assert result.driver == "EVENT_DRIVEN"
    mock_breadth.assert_not_called()


def test_macro_beats_supply():
    """MACRO fires before SUPPLY check when breadth > threshold."""
    a = _asset()
    db = _db_returning(a)

    calls = [[], []]  # no EVENT_DRIVEN events; no RELEASE events

    with (
        patch.object(_das, "_matching_events", side_effect=lambda *a, **kw: calls.pop(0) if calls else []),
        patch.object(_das, "_check_macro_breadth", return_value=0.80),
    ):
        result = attribute_signal(db, asset_id=a.id, signal_move_pct=Decimal("10"), signal_window_days=7)

    assert result.driver == "MACRO"
