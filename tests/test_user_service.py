from __future__ import annotations

import unittest
from datetime import UTC, datetime

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401 — registers all models with Base.metadata
from backend.app.db.base import Base
from backend.app.models.enums import AccessTier
from backend.app.models.user import User
from backend.app.services.user_service import set_user_tier


def _coerce_postgres_types_for_sqlite() -> None:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


def _make_engine():
    _coerce_postgres_types_for_sqlite()
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


class SetUserTierTests(unittest.TestCase):
    def setUp(self):
        self.engine = _make_engine()
        Base.metadata.create_all(self.engine)
        session_local = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
        self.db = session_local()
        self.user = User(discord_user_id="123456789", username="testuser")
        self.db.add(self.user)
        self.db.flush()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def test_sets_access_tier(self):
        set_user_tier(self.db, self.user, AccessTier.PRO)

        self.assertEqual(self.user.access_tier, "pro")

    def test_sets_tier_changed_at(self):
        before = datetime.now(UTC)
        set_user_tier(self.db, self.user, AccessTier.PRO)
        after = datetime.now(UTC)

        # tier_changed_at is timezone-naive (DateTime without tz), so strip tz for comparison
        changed_at = self.user.tier_changed_at.replace(tzinfo=UTC)
        self.assertGreaterEqual(changed_at, before)
        self.assertLessEqual(changed_at, after)

    def test_downgrade_to_free_sets_tier(self):
        set_user_tier(self.db, self.user, AccessTier.PRO)
        set_user_tier(self.db, self.user, AccessTier.FREE)

        self.assertEqual(self.user.access_tier, "free")

    def test_returns_the_user(self):
        result = set_user_tier(self.db, self.user, AccessTier.PRO)

        self.assertIs(result, self.user)

    def test_tier_changed_at_updated_on_second_change(self):
        set_user_tier(self.db, self.user, AccessTier.PRO)
        first_changed_at = self.user.tier_changed_at

        set_user_tier(self.db, self.user, AccessTier.FREE)

        self.assertIsNotNone(self.user.tier_changed_at)
        # The second call must record a timestamp >= the first
        self.assertGreaterEqual(self.user.tier_changed_at, first_changed_at)
