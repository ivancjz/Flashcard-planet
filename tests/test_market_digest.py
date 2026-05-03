from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock
import uuid

import pytest

from backend.app.services.market_digest import should_send_digest, get_digest_candidates


def _user(
    *,
    digest_frequency: str = "daily",
    last_digest_sent_at=None,
    created_at: datetime | None = None,
    trial_started_at: datetime | None = None,
):
    u = MagicMock()
    u.digest_frequency = digest_frequency
    u.last_digest_sent_at = last_digest_sent_at
    u.created_at = created_at or datetime.now(UTC) - timedelta(hours=48)
    u.trial_started_at = trial_started_at
    return u


class TestShouldSendDigest:
    TODAY = date(2026, 5, 4)

    def test_off_user_never_sends(self):
        user = _user(digest_frequency="off")
        assert should_send_digest(user, self.TODAY, has_signals=True) is False

    def test_off_user_never_sends_even_with_old_last_sent(self):
        user = _user(
            digest_frequency="off",
            last_digest_sent_at=datetime(2026, 4, 1, 7, 0, tzinfo=UTC),
        )
        assert should_send_digest(user, self.TODAY, has_signals=True) is False

    def test_daily_user_with_breakout_sends(self):
        user = _user(digest_frequency="daily")
        assert should_send_digest(user, self.TODAY, has_signals=True) is True

    def test_daily_user_no_signals_no_history_sends_weekly_fallback(self):
        user = _user(digest_frequency="daily", last_digest_sent_at=None)
        assert should_send_digest(user, self.TODAY, has_signals=False) is True

    def test_daily_user_no_signals_sent_6_days_ago_does_not_send(self):
        six_days_ago = datetime(2026, 4, 28, 7, 0, tzinfo=UTC)
        user = _user(digest_frequency="daily", last_digest_sent_at=six_days_ago)
        assert should_send_digest(user, self.TODAY, has_signals=False) is False

    def test_daily_user_no_signals_sent_7_days_ago_sends_weekly_fallback(self):
        seven_days_ago = datetime(2026, 4, 27, 7, 0, tzinfo=UTC)
        user = _user(digest_frequency="daily", last_digest_sent_at=seven_days_ago)
        assert should_send_digest(user, self.TODAY, has_signals=False) is True

    def test_weekly_user_sent_6_days_ago_does_not_send(self):
        six_days_ago = datetime(2026, 4, 28, 7, 0, tzinfo=UTC)
        user = _user(digest_frequency="weekly", last_digest_sent_at=six_days_ago)
        assert should_send_digest(user, self.TODAY, has_signals=True) is False

    def test_weekly_user_sent_7_days_ago_sends(self):
        seven_days_ago = datetime(2026, 4, 27, 7, 0, tzinfo=UTC)
        user = _user(digest_frequency="weekly", last_digest_sent_at=seven_days_ago)
        assert should_send_digest(user, self.TODAY, has_signals=True) is True

    def test_24h_grace_period_new_user_does_not_send(self):
        user = _user(
            digest_frequency="daily",
            created_at=datetime.now(UTC) - timedelta(hours=10),
        )
        assert should_send_digest(user, self.TODAY, has_signals=True) is False

    def test_24h_grace_period_uses_trial_started_at_if_set(self):
        user = _user(
            digest_frequency="daily",
            created_at=datetime.now(UTC) - timedelta(hours=48),
            trial_started_at=datetime.now(UTC) - timedelta(hours=10),
        )
        assert should_send_digest(user, self.TODAY, has_signals=True) is False

    def test_user_past_24h_grace_period_sends(self):
        user = _user(
            digest_frequency="daily",
            created_at=datetime.now(UTC) - timedelta(hours=25),
        )
        assert should_send_digest(user, self.TODAY, has_signals=True) is True


def _make_signal_row(
    *,
    asset_id: str = None,
    name: str = "Charizard",
    game: str = "pokemon",
    label: str = "BREAKOUT",
    signal_score: float = 0.9,
    price_delta_pct: float = 15.0,
    current_price: float = 42.0,
):
    row = MagicMock()
    row.asset_id = uuid.UUID(asset_id) if asset_id else uuid.uuid4()
    row.name = name
    row.game = game
    row.label = label
    row.signal_score = signal_score
    row.price_delta_pct = price_delta_pct
    row.current_price = current_price
    return row


class TestGetDigestCandidates:
    def _db_with_signals(self, breakouts=None, moves=None, popular=None):
        db = MagicMock()
        results = []
        for rows in [breakouts or [], moves or [], popular or []]:
            mock_result = MagicMock()
            mock_result.fetchall.return_value = rows
            results.append(mock_result)
        db.execute.side_effect = results
        return db

    def test_returns_max_5_cards(self):
        breakouts = [_make_signal_row() for _ in range(7)]
        db = self._db_with_signals(breakouts=breakouts)
        cards = get_digest_candidates(db, date(2026, 5, 4))
        assert len(cards) <= 5

    def test_breakouts_fill_first(self):
        breakouts = [_make_signal_row(label="BREAKOUT") for _ in range(3)]
        moves = [_make_signal_row(label="MOVE") for _ in range(4)]
        db = self._db_with_signals(breakouts=breakouts, moves=moves)
        cards = get_digest_candidates(db, date(2026, 5, 4))
        signal_types = [c.signal_type for c in cards]
        breakout_count = signal_types.count("BREAKOUT")
        assert breakout_count == 3
        assert len(cards) == 5

    def test_popular_fills_when_no_signals(self):
        popular = [_make_signal_row(label="IDLE") for _ in range(5)]
        db = self._db_with_signals(popular=popular)
        cards = get_digest_candidates(db, date(2026, 5, 4))
        assert len(cards) == 5
        assert all(c.signal_type == "popular" for c in cards)

    def test_returns_empty_when_no_data(self):
        db = self._db_with_signals()
        cards = get_digest_candidates(db, date(2026, 5, 4))
        assert cards == []

    def test_no_duplicate_cards(self):
        shared_id = str(uuid.uuid4())
        breakouts = [_make_signal_row(asset_id=shared_id, label="BREAKOUT")]
        moves = [
            _make_signal_row(asset_id=shared_id, label="MOVE"),
            _make_signal_row(label="MOVE"),
        ]
        db = self._db_with_signals(breakouts=breakouts, moves=moves)
        cards = get_digest_candidates(db, date(2026, 5, 4))
        ids = [c.asset_id for c in cards]
        assert len(ids) == len(set(ids))
