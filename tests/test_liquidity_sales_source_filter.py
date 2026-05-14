"""
tests/test_liquidity_sales_source_filter.py

Integration tests proving that liquidity_service only counts ebay_sold rows
as "sales" (sales_count_7d, sales_count_30d, last_real_sale_at).
pokemon_tcg_api polling rows must NOT be treated as sales.

TDD: written BEFORE the fix. Each test FAILS on current main, PASSES after fix.

Bug 1 from audits/2026-05-01/REPORT.md:
  get_liquidity_snapshots counted ALL non-sample price_history rows as sales,
  including hourly pokemon_tcg_api bulk-refresh polls (~180/card/7d).
  Fix: scope sales_count_7d, sales_count_30d, last_real_sale_at to ebay_sold only.
  Preserve: history_depth and source_count remain all-source.
"""
from __future__ import annotations

import unittest
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


# ── SQLite in-memory setup ─────────────────────────────────────────────────────

def _coerce_postgres_types() -> None:
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


def _make_asset(name: str = "Lickitung") -> Asset:
    return Asset(
        asset_class="TCG",
        game="pokemon",
        name=name,
        set_name="Jungle",
        card_number="58",
        language="en",
        metadata_json={},
    )


def _ph(asset_id, *, price: str, hours_ago: float, source: str) -> PriceHistory:
    return PriceHistory(
        asset_id=asset_id,
        price=Decimal(price),
        currency="USD",
        source=source,
        captured_at=datetime.now(UTC) - timedelta(hours=hours_ago),
        market_segment="raw",
    )


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestLiquiditySalesCountsOnlyEbaySold(unittest.TestCase):
    """
    Core bug: 180 pokemon_tcg_api rows in 7d → current code sets sales_count_7d=180.
    After fix: sales_count_7d must be 0 (no ebay_sold rows).
    """

    def test_tcg_api_polls_do_not_count_as_sales_7d(self):
        """180 hourly pokemon_tcg_api rows must not inflate sales_count_7d."""
        from backend.app.services.liquidity_service import get_liquidity_snapshots
        with _db_session() as db:
            asset = _make_asset()
            db.add(asset)
            db.flush()

            # Simulate 7 days of hourly bulk-refresh polls (the bug scenario)
            for h in range(168):  # 7 days × 24 hours
                db.add(_ph(asset.id, price="2.00", hours_ago=h + 0.5,
                           source="pokemon_tcg_api"))
            db.flush()

            snapshots = get_liquidity_snapshots(db, [asset.id])

        snap = snapshots[asset.id]
        self.assertEqual(
            snap.sales_count_7d, 0,
            f"Expected 0 ebay_sold rows in 7d but got {snap.sales_count_7d}. "
            "pokemon_tcg_api polls must not count as sales."
        )

    def test_tcg_api_polls_do_not_count_as_sales_30d(self):
        """pokemon_tcg_api rows must not inflate sales_count_30d."""
        from backend.app.services.liquidity_service import get_liquidity_snapshots
        with _db_session() as db:
            asset = _make_asset()
            db.add(asset)
            db.flush()

            for h in range(600):  # 25 days of hourly polls
                db.add(_ph(asset.id, price="2.00", hours_ago=h + 0.5,
                           source="pokemon_tcg_api"))
            db.flush()

            snapshots = get_liquidity_snapshots(db, [asset.id])

        snap = snapshots[asset.id]
        self.assertEqual(
            snap.sales_count_30d, 0,
            f"Expected 0 but got {snap.sales_count_30d}. "
            "pokemon_tcg_api polls must not count toward sales_count_30d."
        )

    def test_ebay_sold_rows_do_not_count_as_sales_after_deprecation(self):
        """ebay_sold deprecated 2026-05-14 — sales_count_7d must be 0 even with ebay_sold rows present."""
        from backend.app.services.liquidity_service import get_liquidity_snapshots
        with _db_session() as db:
            asset = _make_asset()
            db.add(asset)
            db.flush()

            # ebay_sold rows within 7-day window — must NOT count after deprecation
            db.add(_ph(asset.id, price="1.66", hours_ago=1, source="ebay_sold"))
            db.add(_ph(asset.id, price="1.80", hours_ago=48, source="ebay_sold"))
            db.add(_ph(asset.id, price="1.50", hours_ago=100, source="ebay_sold"))

            for h in range(24):
                db.add(_ph(asset.id, price="2.18", hours_ago=h + 0.5,
                           source="pokemon_tcg_api"))
            db.flush()

            snapshots = get_liquidity_snapshots(db, [asset.id])

        snap = snapshots[asset.id]
        self.assertEqual(
            snap.sales_count_7d, 0,
            f"ebay_sold is deprecated — sales_count_7d must be 0, got {snap.sales_count_7d}."
        )


class TestLiquidityLastSaleAtUsesOnlyEbaySold(unittest.TestCase):
    """
    last_real_sale_at must reflect the last ebay_sold row,
    not the last pokemon_tcg_api poll.
    """

    def test_last_real_sale_at_is_none_with_no_ebay_data(self):
        """A card with only TCG polls should have last_real_sale_at = None."""
        from backend.app.services.liquidity_service import get_liquidity_snapshots
        with _db_session() as db:
            asset = _make_asset()
            db.add(asset)
            db.flush()

            # Only TCG polls, no eBay data
            for h in range(24):
                db.add(_ph(asset.id, price="2.18", hours_ago=h + 0.5,
                           source="pokemon_tcg_api"))
            db.flush()

            snapshots = get_liquidity_snapshots(db, [asset.id])

        snap = snapshots[asset.id]
        self.assertIsNone(
            snap.last_real_sale_at,
            f"Expected None for last_real_sale_at (no eBay data) but got {snap.last_real_sale_at}."
        )

    def test_last_real_sale_at_uses_ebay_sold_timestamp(self):
        """After ebay_sold deprecation (2026-05-14), last_real_sale_at is always None.

        Previously this tested that ebay_sold timestamps were surfaced here.
        Now ebay_sold is excluded from the query — last_real_sale_at must be None
        even when ebay_sold rows are present in the DB.
        """
        from backend.app.services.liquidity_service import get_liquidity_snapshots
        with _db_session() as db:
            asset = _make_asset()
            db.add(asset)
            db.flush()

            ebay_ts = datetime.now(UTC) - timedelta(hours=36)
            db.add(PriceHistory(
                asset_id=asset.id, price=Decimal("1.66"), currency="USD",
                source="ebay_sold", captured_at=ebay_ts, market_segment="raw",
            ))

            for h in range(24):
                db.add(_ph(asset.id, price="2.18", hours_ago=h + 0.5,
                           source="pokemon_tcg_api"))
            db.flush()

            snapshots = get_liquidity_snapshots(db, [asset.id])

        snap = snapshots[asset.id]
        self.assertIsNone(
            snap.last_real_sale_at,
            f"last_real_sale_at must be None after ebay_sold deprecation, got {snap.last_real_sale_at}."
        )


class TestLiquidityPreservesHistoryDepthAndSourceCount(unittest.TestCase):
    """
    history_depth and source_count should reflect ALL non-sample sources,
    not just ebay_sold. These are data-richness indicators, not sales indicators.
    """

    def test_history_depth_excludes_ebay_sold_after_deprecation(self):
        """180 TCG + 2 eBay rows → history_depth should be 180 (ebay_sold excluded after deprecation)."""
        from backend.app.services.liquidity_service import get_liquidity_snapshots
        with _db_session() as db:
            asset = _make_asset()
            db.add(asset)
            db.flush()

            for h in range(180):
                db.add(_ph(asset.id, price="2.00", hours_ago=h + 0.5,
                           source="pokemon_tcg_api"))
            db.add(_ph(asset.id, price="1.66", hours_ago=50, source="ebay_sold"))
            db.add(_ph(asset.id, price="1.80", hours_ago=200, source="ebay_sold"))
            db.flush()

            snapshots = get_liquidity_snapshots(db, [asset.id])

        snap = snapshots[asset.id]
        self.assertEqual(
            snap.history_depth, 180,
            f"history_depth must exclude ebay_sold rows (deprecated 2026-05-14); "
            f"expected 180 TCG rows, got {snap.history_depth}."
        )

    def test_source_count_includes_all_non_sample_sources_including_deprecated(self):
        """A card with TCG + eBay rows has source_count=2 — ebay_sold still counted in distinct sources.

        source_count is a data-presence indicator, not an active-sales indicator.
        ebay_sold rows are in the DB and represent historical data richness.
        """
        from backend.app.services.liquidity_service import get_liquidity_snapshots
        with _db_session() as db:
            asset = _make_asset()
            db.add(asset)
            db.flush()

            db.add(_ph(asset.id, price="2.00", hours_ago=1, source="pokemon_tcg_api"))
            db.add(_ph(asset.id, price="1.66", hours_ago=2, source="ebay_sold"))
            db.flush()

            snapshots = get_liquidity_snapshots(db, [asset.id])

        snap = snapshots[asset.id]
        self.assertEqual(
            snap.source_count, 2,
            f"source_count should be 2 (pokemon_tcg_api + ebay_sold present in DB) but got {snap.source_count}."
        )

    def test_source_count_is_one_for_tcg_only_card(self):
        """A card with only TCG rows should have source_count=1."""
        from backend.app.services.liquidity_service import get_liquidity_snapshots
        with _db_session() as db:
            asset = _make_asset()
            db.add(asset)
            db.flush()

            for h in range(5):
                db.add(_ph(asset.id, price="2.00", hours_ago=h + 0.5,
                           source="pokemon_tcg_api"))
            db.flush()

            snapshots = get_liquidity_snapshots(db, [asset.id])

        snap = snapshots[asset.id]
        self.assertEqual(
            snap.source_count, 1,
            f"Expected source_count=1 for TCG-only card but got {snap.source_count}."
        )
