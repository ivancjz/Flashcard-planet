"""
tests/test_upgrade_flow.py

Covers:
  - permissions.py  extended feature matrix + limit helpers
  - signals_feed_service  free-tier truncation logic
  - upgrade_service  full request lifecycle

Adapted to this project:
  - User.id is uuid.UUID (not int)
  - SQLAlchemy 2.x style (select / db.scalars)
  - set_user_tier(db, user_obj, AccessTier.PRO) signature
"""
from __future__ import annotations

import unittest
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401 — registers all models with Base.metadata
from backend.app.db.base import Base
from backend.app.models.enums import AccessTier
from backend.app.models.upgrade_request import UpgradeRequest
from backend.app.models.user import User


# ── SQLite helpers ────────────────────────────────────────────────────────────

def _coerce_postgres_types_for_sqlite() -> None:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


@contextmanager
def session_scope():
    _coerce_postgres_types_for_sqlite()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with session_local() as db_session:
        yield db_session
    Base.metadata.drop_all(engine)


def _make_user(db: Session, *, tier: str = "free") -> User:
    user = User(discord_user_id=str(uuid.uuid4())[:20], access_tier=tier)
    db.add(user)
    db.flush()
    return user


# ── A1: permissions extended feature matrix ───────────────────────────────────

class TestCanGate(unittest.TestCase):
    def test_free_has_no_features(self):
        from backend.app.core.permissions import Feature, can
        for feature in Feature:
            self.assertFalse(can("free", feature))

    def test_pro_has_all_features(self):
        from backend.app.core.permissions import Feature, can
        for feature in Feature:
            self.assertTrue(can("pro", feature))

    def test_unknown_tier_treated_as_free(self):
        from backend.app.core.permissions import Feature, can
        self.assertFalse(can("enterprise", Feature.PRICE_HISTORY_FULL))
        self.assertFalse(can("", Feature.SIGNALS_FULL_FEED))

    def test_case_insensitive(self):
        from backend.app.core.permissions import Feature, can
        self.assertTrue(can("PRO", Feature.PRICE_HISTORY_FULL))
        self.assertFalse(can("FREE", Feature.PRICE_HISTORY_FULL))

    def test_get_capabilities_free_is_empty(self):
        from backend.app.core.permissions import get_capabilities
        self.assertEqual(get_capabilities("free"), frozenset())

    def test_get_capabilities_pro_is_complete(self):
        from backend.app.core.permissions import Feature, get_capabilities
        self.assertEqual(get_capabilities("pro"), frozenset(Feature))


class TestLimitHelpers(unittest.TestCase):
    def test_history_days_free(self):
        from backend.app.core.permissions import FREE_HISTORY_DAYS, history_days
        self.assertEqual(history_days("free"), FREE_HISTORY_DAYS)

    def test_history_days_pro(self):
        from backend.app.core.permissions import PRO_HISTORY_DAYS, history_days
        self.assertEqual(history_days("pro"), PRO_HISTORY_DAYS)

    def test_alert_limit_free(self):
        from backend.app.core.permissions import FREE_ALERT_LIMIT, alert_limit
        self.assertEqual(alert_limit("free"), FREE_ALERT_LIMIT)

    def test_alert_limit_pro_is_none(self):
        from backend.app.core.permissions import alert_limit
        self.assertIsNone(alert_limit("pro"))

    def test_watchlist_limit_free(self):
        from backend.app.core.permissions import FREE_WATCHLIST_LIMIT, watchlist_limit
        self.assertEqual(watchlist_limit("free"), FREE_WATCHLIST_LIMIT)

    def test_watchlist_limit_pro_is_none(self):
        from backend.app.core.permissions import watchlist_limit
        self.assertIsNone(watchlist_limit("pro"))

    def test_signals_limit_free(self):
        from backend.app.core.permissions import FREE_SIGNALS_LIMIT, signals_limit
        self.assertEqual(signals_limit("free"), FREE_SIGNALS_LIMIT)

    def test_signals_limit_pro_is_none(self):
        from backend.app.core.permissions import signals_limit
        self.assertIsNone(signals_limit("pro"))


# ── A1: signals_feed_service free-tier truncation ─────────────────────────────

class TestSignalsFeedTruncation(unittest.TestCase):
    """
    Mocks the DB query to verify tier-gating without a live database.
    Matches our build_signals_feed(db, access_tier, label_filter) signature.
    """

    def _build_mock_db(self, signal_asset_pairs: list) -> MagicMock:
        """Return a mock db whose execute(...).all() returns signal_asset_pairs."""
        db = MagicMock(spec=Session)
        execute_result = MagicMock()
        execute_result.all.return_value = signal_asset_pairs
        db.execute.return_value = execute_result
        return db

    def _make_signal_asset_pair(self, *, confidence: int = 80, label: str = "BREAKOUT"):
        sig = MagicMock()
        sig.asset_id = uuid.uuid4()
        sig.label = label
        sig.confidence = confidence
        sig.computed_at = datetime(2026, 4, 1, tzinfo=UTC)
        sig.explanation = "Price spike detected"
        sig.liquidity_score = 70

        asset = MagicMock()
        asset.external_id = f"ext-{uuid.uuid4().hex[:8]}"
        asset.name = "Charizard"
        asset.set_name = "Base Set"

        return (sig, asset)

    def test_free_tier_caps_at_five(self):
        from backend.app.services.signals_feed_service import build_signals_feed
        pairs = [self._make_signal_asset_pair() for _ in range(10)]
        db = self._build_mock_db(pairs)

        result = build_signals_feed(db, "free")

        self.assertEqual(len(result.rows), 5)
        self.assertTrue(result.truncated)
        self.assertEqual(result.hidden_count, 5)

    def test_free_tier_hides_confidence(self):
        from backend.app.services.signals_feed_service import build_signals_feed
        pairs = [self._make_signal_asset_pair(confidence=90)]
        db = self._build_mock_db(pairs)

        result = build_signals_feed(db, "free")

        self.assertFalse(result.show_confidence)
        self.assertIsNone(result.rows[0].confidence)

    def test_free_tier_hides_explanation(self):
        from backend.app.services.signals_feed_service import build_signals_feed
        pairs = [self._make_signal_asset_pair()]
        db = self._build_mock_db(pairs)

        result = build_signals_feed(db, "free")

        self.assertFalse(result.show_explanation)
        self.assertIsNone(result.rows[0].explanation)

    def test_pro_tier_no_truncation(self):
        from backend.app.services.signals_feed_service import build_signals_feed
        pairs = [self._make_signal_asset_pair() for _ in range(20)]
        db = self._build_mock_db(pairs)

        result = build_signals_feed(db, "pro")

        self.assertFalse(result.truncated)
        self.assertEqual(result.hidden_count, 0)
        self.assertTrue(result.show_confidence)

    def test_pro_tier_shows_explanation(self):
        from backend.app.services.signals_feed_service import build_signals_feed
        pairs = [self._make_signal_asset_pair()]
        db = self._build_mock_db(pairs)

        result = build_signals_feed(db, "pro")

        self.assertEqual(result.rows[0].explanation, "Price spike detected")

    def test_no_truncation_when_fewer_than_limit(self):
        from backend.app.services.signals_feed_service import build_signals_feed
        pairs = [self._make_signal_asset_pair() for _ in range(3)]
        db = self._build_mock_db(pairs)

        result = build_signals_feed(db, "free")

        self.assertFalse(result.truncated)
        self.assertEqual(result.hidden_count, 0)


# ── A4: upgrade_service lifecycle ─────────────────────────────────────────────

class TestUpgradeServiceSubmit(unittest.TestCase):
    def test_submit_creates_pending_request(self):
        from backend.app.services.upgrade_service import submit_upgrade_request
        with session_scope() as db:
            user = _make_user(db, tier="free")
            result = submit_upgrade_request(db, user_id=user.id, note="please")
        self.assertTrue(result.ok)
        self.assertIsNotNone(result.request_id)
        self.assertEqual(result.status, "pending")

    def test_submit_blocked_if_already_pro(self):
        from backend.app.services.upgrade_service import submit_upgrade_request
        with session_scope() as db:
            user = _make_user(db, tier="pro")
            result = submit_upgrade_request(db, user_id=user.id)
        self.assertFalse(result.ok)
        self.assertIn("already Pro", result.error)

    def test_submit_idempotent_returns_existing(self):
        from backend.app.services.upgrade_service import submit_upgrade_request
        with session_scope() as db:
            user = _make_user(db, tier="free")
            r1 = submit_upgrade_request(db, user_id=user.id)
            r2 = submit_upgrade_request(db, user_id=user.id)
        self.assertTrue(r1.ok)
        self.assertTrue(r2.ok)
        self.assertEqual(r1.request_id, r2.request_id)

    def test_submit_returns_error_for_missing_user(self):
        from backend.app.services.upgrade_service import submit_upgrade_request
        with session_scope() as db:
            result = submit_upgrade_request(db, user_id=uuid.uuid4())
        self.assertFalse(result.ok)
        self.assertIn("not found", result.error.lower())


class TestUpgradeServiceApprove(unittest.TestCase):
    def test_approve_sets_status_and_promotes_user(self):
        from backend.app.services.upgrade_service import (
            approve_upgrade_request,
            submit_upgrade_request,
        )
        with session_scope() as db:
            user = _make_user(db, tier="free")
            submit_result = submit_upgrade_request(db, user_id=user.id)
            result = approve_upgrade_request(db, request_id=submit_result.request_id)
            db.refresh(user)

        self.assertTrue(result.ok)
        self.assertEqual(result.status, "approved")
        self.assertEqual(user.access_tier, "pro")

    def test_approve_fails_if_not_pending(self):
        from backend.app.services.upgrade_service import (
            approve_upgrade_request,
            submit_upgrade_request,
        )
        with session_scope() as db:
            user = _make_user(db, tier="free")
            submit_result = submit_upgrade_request(db, user_id=user.id)
            approve_upgrade_request(db, request_id=submit_result.request_id)
            result = approve_upgrade_request(db, request_id=submit_result.request_id)

        self.assertFalse(result.ok)
        self.assertIn("already", result.error)

    def test_approve_fails_for_missing_request(self):
        from backend.app.services.upgrade_service import approve_upgrade_request
        with session_scope() as db:
            result = approve_upgrade_request(db, request_id=uuid.uuid4())
        self.assertFalse(result.ok)


class TestUpgradeServiceReject(unittest.TestCase):
    def test_reject_sets_status(self):
        from backend.app.services.upgrade_service import (
            reject_upgrade_request,
            submit_upgrade_request,
        )
        with session_scope() as db:
            user = _make_user(db, tier="free")
            submit_result = submit_upgrade_request(db, user_id=user.id)
            result = reject_upgrade_request(db, request_id=submit_result.request_id)
            db.refresh(user)

        self.assertTrue(result.ok)
        self.assertEqual(result.status, "rejected")
        self.assertEqual(user.access_tier, "free")  # unchanged

    def test_reject_fails_for_missing_request(self):
        from backend.app.services.upgrade_service import reject_upgrade_request
        with session_scope() as db:
            result = reject_upgrade_request(db, request_id=uuid.uuid4())
        self.assertFalse(result.ok)


class TestUpgradeServiceCancel(unittest.TestCase):
    def test_cancel_pending_request(self):
        from backend.app.services.upgrade_service import (
            cancel_upgrade_request,
            submit_upgrade_request,
        )
        with session_scope() as db:
            user = _make_user(db, tier="free")
            submit_upgrade_request(db, user_id=user.id)
            result = cancel_upgrade_request(db, user_id=user.id)

        self.assertTrue(result.ok)
        self.assertEqual(result.status, "cancelled")

    def test_cancel_returns_error_if_no_pending(self):
        from backend.app.services.upgrade_service import cancel_upgrade_request
        with session_scope() as db:
            user = _make_user(db, tier="free")
            result = cancel_upgrade_request(db, user_id=user.id)
        self.assertFalse(result.ok)


class TestGetUpgradeStatus(unittest.TestCase):
    def test_pro_user_returns_pro_tier(self):
        from backend.app.services.upgrade_service import get_upgrade_status
        with session_scope() as db:
            user = _make_user(db, tier="pro")
            status = get_upgrade_status(db, user_id=user.id)

        self.assertEqual(status["tier"], "pro")
        self.assertIsNone(status["request_status"])

    def test_free_with_pending_request(self):
        from backend.app.services.upgrade_service import (
            get_upgrade_status,
            submit_upgrade_request,
        )
        with session_scope() as db:
            user = _make_user(db, tier="free")
            submit_upgrade_request(db, user_id=user.id)
            status = get_upgrade_status(db, user_id=user.id)

        self.assertEqual(status["tier"], "free")
        self.assertEqual(status["request_status"], "pending")
        self.assertIn("request_id", status)

    def test_free_with_no_request(self):
        from backend.app.services.upgrade_service import get_upgrade_status
        with session_scope() as db:
            user = _make_user(db, tier="free")
            status = get_upgrade_status(db, user_id=user.id)

        self.assertEqual(status["tier"], "free")
        self.assertIsNone(status["request_status"])
