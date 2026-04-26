"""
tests/test_signal_segment_filter.py

Integration tests proving that the signal engine only reads market_segment='raw'
price_history rows.  Uses SQLite in-memory with real SQLAlchemy queries.

TDD: these tests are written BEFORE the filter is added to signal_service.py.
Each test should FAIL with the current code, then PASS after the filter is added.
"""
from __future__ import annotations

import unittest
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401 — registers all models
from backend.app.db.base import Base
from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory


# ── Shared SQLite test infrastructure ─────────────────────────────────────────

def _coerce_postgres_types() -> None:
    """Replace PostgreSQL-only types so SQLite can create the schema."""
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()


@contextmanager
def _db_session():
    _coerce_postgres_types()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as session:
        yield session
    Base.metadata.drop_all(engine)


def _make_asset(name: str = "Charizard") -> Asset:
    return Asset(
        asset_class="TCG",
        category="Pokemon",
        name=name,
        set_name="Base Set",
        card_number="4",
        language="en",
        variant="Holo",
        metadata_json={},
    )


def _ph(asset_id, *, price: str, days_ago: int, source: str = "ebay_sold",
        segment: str = "raw") -> PriceHistory:
    """Helper: create a PriceHistory row with explicit market_segment."""
    return PriceHistory(
        asset_id=asset_id,
        price=Decimal(price),
        currency="USD",
        source=source,
        captured_at=datetime.now(UTC) - timedelta(days=days_ago),
        market_segment=segment,
    )


# ── Test 1: graded rows excluded from baseline & current ─────────────────────

class TestSignalExcludesGradedRows(unittest.TestCase):
    """5 raw + 5 graded rows in baseline window.
    After filtering: baseline_n == 5, graded prices do NOT influence median."""

    def test_graded_rows_excluded_from_baseline_n(self):
        from backend.app.services.signal_service import _compute_delta_batch
        with _db_session() as db:
            asset = _make_asset()
            db.add(asset)
            db.flush()
            now = datetime.now(UTC)

            # Baseline window: older than 7 days
            for i in range(5):
                db.add(_ph(asset.id, price="10.00", days_ago=10 + i, segment="raw"))
            for i in range(5):
                db.add(_ph(asset.id, price="999.00", days_ago=10 + i, segment="psa_10"))

            # Current window: last 24h
            db.add(_ph(asset.id, price="11.00", days_ago=0, segment="raw"))
            db.add(_ph(asset.id, price="888.00", days_ago=0, segment="psa_10"))

            db.flush()

            result = _compute_delta_batch(
                db,
                [asset.id],
                baseline_window_days=7,
                current_window_hours=24,
                source_weights={"ebay_sold": 1.0},
                now=now,
            )

        delta, ctx = result[asset.id]
        self.assertEqual(ctx["baseline_n"], 5,
                         "baseline_n should count only raw rows")
        self.assertEqual(ctx["current_n"], 1,
                         "current_n should count only raw rows")
        # Baseline median of [10,10,10,10,10] = 10; current = 11; delta = +10%
        self.assertIsNotNone(delta)
        self.assertEqual(delta, Decimal("10.00"))

    def test_graded_prices_do_not_inflate_current_median(self):
        """graded rows at 999 must not pollute the current price calculation."""
        from backend.app.services.signal_service import _compute_delta_batch
        with _db_session() as db:
            asset = _make_asset()
            db.add(asset)
            db.flush()
            now = datetime.now(UTC)

            db.add(_ph(asset.id, price="100.00", days_ago=10, segment="raw"))
            db.add(_ph(asset.id, price="100.00", days_ago=11, segment="raw"))
            db.add(_ph(asset.id, price="100.00", days_ago=12, segment="raw"))

            db.add(_ph(asset.id, price="110.00", days_ago=0, segment="raw"))
            db.add(_ph(asset.id, price="999.00", days_ago=0, segment="psa_10"))
            db.add(_ph(asset.id, price="999.00", days_ago=0, segment="bgs_9_5"))

            db.flush()

            result = _compute_delta_batch(
                db, [asset.id],
                baseline_window_days=7, current_window_hours=24,
                source_weights={"ebay_sold": 1.0}, now=now,
            )

        delta, ctx = result[asset.id]
        self.assertEqual(ctx["current_n"], 1)
        self.assertEqual(float(ctx["current_price"]), 110.0)


# ── Test 2: unknown rows excluded ─────────────────────────────────────────────

class TestSignalExcludesUnknownRows(unittest.TestCase):
    """3 raw + 2 unknown rows → baseline_n == 3."""

    def test_unknown_rows_excluded(self):
        from backend.app.services.signal_service import _compute_delta_batch
        with _db_session() as db:
            asset = _make_asset()
            db.add(asset)
            db.flush()
            now = datetime.now(UTC)

            for i in range(3):
                db.add(_ph(asset.id, price="50.00", days_ago=10 + i, segment="raw"))
            for i in range(2):
                db.add(_ph(asset.id, price="500.00", days_ago=10 + i, segment="unknown"))

            db.add(_ph(asset.id, price="55.00", days_ago=0, segment="raw"))

            db.flush()

            result = _compute_delta_batch(
                db, [asset.id],
                baseline_window_days=7, current_window_hours=24,
                source_weights={"ebay_sold": 1.0}, now=now,
            )

        delta, ctx = result[asset.id]
        self.assertEqual(ctx["baseline_n"], 3)
        self.assertEqual(ctx["current_n"], 1)


# ── Test 3: no raw baseline → no_baseline_data ────────────────────────────────

class TestNoRawBaselineYieldsNoBaaselineData(unittest.TestCase):
    """Only graded rows in baseline window → reason == 'no_baseline_data'."""

    def test_graded_only_baseline_returns_no_baseline_data(self):
        from backend.app.services.signal_service import _compute_delta_batch
        with _db_session() as db:
            asset = _make_asset()
            db.add(asset)
            db.flush()
            now = datetime.now(UTC)

            for i in range(5):
                db.add(_ph(asset.id, price="999.00", days_ago=10 + i, segment="psa_10"))
            db.add(_ph(asset.id, price="50.00", days_ago=0, segment="raw"))

            db.flush()

            result = _compute_delta_batch(
                db, [asset.id],
                baseline_window_days=7, current_window_hours=24,
                source_weights={"ebay_sold": 1.0}, now=now,
            )

        delta, ctx = result[asset.id]
        self.assertIsNone(delta)
        self.assertEqual(ctx.get("reason"), "no_baseline_data")


# ── Test 4: no raw current → no_current_data ─────────────────────────────────

class TestNoRawCurrentYieldsNoCurrentData(unittest.TestCase):
    """Raw baseline exists but only graded rows in current window → reason == 'no_current_data'."""

    def test_graded_only_current_returns_no_current_data(self):
        from backend.app.services.signal_service import _compute_delta_batch
        with _db_session() as db:
            asset = _make_asset()
            db.add(asset)
            db.flush()
            now = datetime.now(UTC)

            # Baseline: raw
            for i in range(3):
                db.add(_ph(asset.id, price="10.00", days_ago=10 + i, segment="raw"))
            # Current window: graded only
            db.add(_ph(asset.id, price="999.00", days_ago=0, segment="psa_10"))
            db.add(_ph(asset.id, price="999.00", days_ago=0, segment="bgs_9_5"))

            db.flush()

            result = _compute_delta_batch(
                db, [asset.id],
                baseline_window_days=7, current_window_hours=24,
                source_weights={"ebay_sold": 1.0}, now=now,
            )

        delta, ctx = result[asset.id]
        self.assertIsNone(delta)
        self.assertEqual(ctx.get("reason"), "no_current_data")


# ── Test 5: TCGPlayer rows (market_segment='raw') still included ───────────────

class TestTCGPlayerRowsIncluded(unittest.TestCase):
    """pokemon_tcg_api rows set market_segment='raw' by PR A.
    They must still participate in signal computation after the filter is added."""

    def test_tcgplayer_raw_rows_contribute_to_signal(self):
        from backend.app.services.signal_service import _compute_delta_batch
        with _db_session() as db:
            asset = _make_asset()
            db.add(asset)
            db.flush()
            now = datetime.now(UTC)

            # TCGPlayer baseline (always raw)
            for i in range(3):
                db.add(_ph(asset.id, price="100.00", days_ago=10 + i,
                           source="pokemon_tcg_api", segment="raw"))
            # TCGPlayer current (always raw)
            db.add(_ph(asset.id, price="120.00", days_ago=0,
                       source="pokemon_tcg_api", segment="raw"))

            db.flush()

            result = _compute_delta_batch(
                db, [asset.id],
                baseline_window_days=7, current_window_hours=24,
                source_weights={"pokemon_tcg_api": 1.0}, now=now,
            )

        delta, ctx = result[asset.id]
        self.assertIsNotNone(delta, "TCGPlayer raw rows must produce a signal")
        self.assertEqual(ctx["baseline_n"], 3)
        self.assertEqual(delta, Decimal("20.00"))


# ── Test 6: _get_active_asset_ids only counts raw rows ─────────────────────────

class TestGetActiveAssetIdsRawOnly(unittest.TestCase):
    """Assets with only graded/unknown data should NOT appear in active list."""

    def test_graded_only_asset_not_active(self):
        from backend.app.services.signal_service import _get_active_asset_ids
        with _db_session() as db:
            raw_asset = _make_asset("RawCard")
            graded_asset = _make_asset("GradedCard")
            db.add(raw_asset)
            db.add(graded_asset)
            db.flush()

            db.add(_ph(raw_asset.id, price="10.00", days_ago=1, segment="raw"))
            db.add(_ph(graded_asset.id, price="999.00", days_ago=1, segment="psa_10"))

            db.flush()

            active = _get_active_asset_ids(db)

        self.assertIn(raw_asset.id, active)
        self.assertNotIn(graded_asset.id, active)

    def test_tcgplayer_raw_asset_is_active(self):
        """TCGPlayer asset (market_segment='raw') appears in active list."""
        from backend.app.services.signal_service import _get_active_asset_ids
        with _db_session() as db:
            asset = _make_asset("TCGCard")
            db.add(asset)
            db.flush()

            db.add(_ph(asset.id, price="50.00", days_ago=1,
                       source="pokemon_tcg_api", segment="raw"))
            db.flush()

            active = _get_active_asset_ids(db)

        self.assertIn(asset.id, active)


# ── Test 7: _get_recent_prices_for_prediction filters graded rows ──────────────

class TestPredictionFilterRaw(unittest.TestCase):
    """Prediction feed must exclude graded rows."""

    def test_prediction_excludes_graded_rows(self):
        from backend.app.services.signal_service import _get_recent_prices_for_prediction
        with _db_session() as db:
            asset = _make_asset()
            db.add(asset)
            db.flush()

            for i in range(3):
                db.add(_ph(asset.id, price=str(10 + i), days_ago=i, segment="raw"))
            for i in range(5):
                db.add(_ph(asset.id, price="999.00", days_ago=i, segment="psa_10"))

            db.flush()

            result = _get_recent_prices_for_prediction(db, [asset.id])

        prices = [float(p) for p, _ in result.get(asset.id, [])]
        self.assertEqual(len(prices), 3, "Only 3 raw rows expected")
        self.assertNotIn(999.0, prices, "Graded price must not appear")
