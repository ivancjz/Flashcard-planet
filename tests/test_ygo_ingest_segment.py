"""
tests/test_ygo_ingest_segment.py

TDD tests for the YGO market_segment fix:
  1. ingest_ygo_sets must write market_segment='raw' on every PriceHistory row
  2. YGO price rows with market_segment='raw' must not be excluded by PR B's signal filter

Written BEFORE the one-line fix in ygo.py — both tests should FAIL until
market_segment='raw' is added to the pg_insert call.
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import JSON, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
from backend.app.db.base import Base
from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory


# ── SQLite in-memory session ──────────────────────────────────────────────────

def _coerce_postgres_types() -> None:
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()


@contextmanager
def _session():
    _coerce_postgres_types()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as db:
        yield db
    Base.metadata.drop_all(engine)


# ── Fake YGOPRODeck API data ──────────────────────────────────────────────────

_FAKE_RAW_CARD = {
    "id": 89631139,
    "name": "Blue-Eyes White Dragon",
    "type": "Normal Monster",
    "card_images": [{"image_url_small": "https://example.com/img.jpg"}],
    "atk": 3000, "def": 2500, "level": 8, "race": "Dragon", "attribute": "LIGHT",
}
_FAKE_ENTRY = {
    "set_code": "LOB-001",
    "set_name": "Legend of Blue Eyes White Dragon",
    "set_rarity": "Ultra Rare",
    "set_price": "62.15",
}


# ── Test 1: ingest writes market_segment='raw' ────────────────────────────────

class TestYgoIngestSetsMarketSegmentRaw:
    """ingest_ygo_sets must set market_segment='raw' on every PriceHistory row it writes."""

    def _make_client_mock(self, entries):
        """Return a mock YugiohClient whose class-level make_external_id still works."""
        from backend.app.ingestion.game_data.yugioh_client import YugiohClient as RealClient
        mock_client = patch("backend.app.ingestion.ygo.YugiohClient")
        mock_sleep = patch("backend.app.ingestion.ygo.time.sleep")
        return mock_client, mock_sleep, RealClient.make_external_id, entries

    def test_market_segment_is_raw_on_inserted_row(self):
        from backend.app.ingestion.ygo import ingest_ygo_sets
        from backend.app.ingestion.game_data.yugioh_client import YugiohClient as RealClient

        with _session() as db:
            with (
                patch("backend.app.ingestion.ygo.YugiohClient") as MockClient,
                patch("backend.app.ingestion.ygo.time.sleep"),
            ):
                MockClient.make_external_id.side_effect = RealClient.make_external_id
                mock_instance = MockClient.return_value
                mock_instance.fetch_set_entries.return_value = [(_FAKE_RAW_CARD, _FAKE_ENTRY)]
                mock_instance.rate_limit_per_second = 10.0

                ingest_ygo_sets(db, set_codes=["LOB"])

            rows = db.execute(select(PriceHistory)).scalars().all()

        assert len(rows) == 1, "expected exactly one price_history row"
        assert rows[0].market_segment == 'raw', (
            f"market_segment should be 'raw', got {rows[0].market_segment!r}"
        )

    def test_market_segment_is_raw_for_multiple_entries(self):
        """All rows written in one ingest run must have market_segment='raw'."""
        from backend.app.ingestion.ygo import ingest_ygo_sets
        from backend.app.ingestion.game_data.yugioh_client import YugiohClient as RealClient

        entries = [
            (
                {**_FAKE_RAW_CARD, "id": i, "name": f"Card {i}"},
                {**_FAKE_ENTRY, "set_code": f"LOB-{i:03d}"},
            )
            for i in range(1, 4)  # 3 cards
        ]

        with _session() as db:
            with (
                patch("backend.app.ingestion.ygo.YugiohClient") as MockClient,
                patch("backend.app.ingestion.ygo.time.sleep"),
            ):
                MockClient.make_external_id.side_effect = RealClient.make_external_id
                mock_instance = MockClient.return_value
                mock_instance.fetch_set_entries.return_value = entries
                mock_instance.rate_limit_per_second = 10.0

                ingest_ygo_sets(db, set_codes=["LOB"])

            rows = db.execute(select(PriceHistory)).scalars().all()

        assert len(rows) == 3
        for row in rows:
            assert row.market_segment == 'raw', (
                f"row {row.id} has market_segment={row.market_segment!r}, expected 'raw'"
            )


# ── Test 2: YGO raw rows pass the signal engine filter ────────────────────────

class TestYgoSignalPassesSegmentFilter:
    """YGO PriceHistory rows with market_segment='raw' must NOT be excluded
    by the signal engine's filter. If this test fails after the ingest fix,
    there is a secondary filter blocking YGO data from signal computation."""

    def _make_ygo_asset(self) -> Asset:
        return Asset(
            asset_class="TCG",
            game="yugioh",
            category="Yu-Gi-Oh",
            name="Blue-Eyes White Dragon",
            set_name="LOB",
            card_number="LOB-001",
            language="EN",
            variant="Ultra Rare",
            metadata_json={},
        )

    def _ph(self, asset_id, *, price: str, days_ago: int) -> PriceHistory:
        return PriceHistory(
            asset_id=asset_id,
            price=Decimal(price),
            currency="USD",
            source="ygoprodeck_api",
            captured_at=datetime.now(UTC) - timedelta(days=days_ago),
            market_segment='raw',
        )

    def test_ygo_raw_rows_contribute_to_baseline(self):
        """_compute_delta_batch must include ygoprodeck_api rows with market_segment='raw'."""
        from backend.app.services.signal_service import _compute_delta_batch

        with _session() as db:
            asset = self._make_ygo_asset()
            db.add(asset)
            db.flush()
            now = datetime.now(UTC)

            # 3 raw YGO rows in baseline window
            for i in range(3):
                db.add(self._ph(asset.id, price="60.00", days_ago=10 + i))
            # 2 raw YGO rows in current window
            db.add(self._ph(asset.id, price="75.00", days_ago=0))
            db.add(self._ph(asset.id, price="74.00", days_ago=0))
            db.flush()

            result = _compute_delta_batch(
                db, [asset.id],
                baseline_window_days=7,
                current_window_hours=24,
                source_weights={"ygoprodeck_api": 1.0},
                now=now,
            )

        delta, ctx = result[asset.id]
        assert delta is not None, (
            f"YGO raw rows produced no delta — signal filter may be excluding ygoprodeck_api. "
            f"ctx={ctx}"
        )
        assert ctx["baseline_n"] == 3, f"expected baseline_n=3, got {ctx['baseline_n']}"
        assert ctx["current_n"] == 2, f"expected current_n=2, got {ctx['current_n']}"

    def test_ygo_null_segment_rows_are_excluded(self):
        """Confirms that NULL market_segment YGO rows (the pre-fix state) are excluded.
        This test documents the bug and validates that the migration is necessary."""
        from backend.app.services.signal_service import _compute_delta_batch

        with _session() as db:
            asset = self._make_ygo_asset()
            db.add(asset)
            db.flush()
            now = datetime.now(UTC)

            # Baseline rows with market_segment=None (pre-fix state)
            for i in range(3):
                db.add(PriceHistory(
                    asset_id=asset.id, price=Decimal("60.00"), currency="USD",
                    source="ygoprodeck_api",
                    captured_at=datetime.now(UTC) - timedelta(days=10 + i),
                    market_segment=None,  # the bug
                ))
            db.flush()

            result = _compute_delta_batch(
                db, [asset.id],
                baseline_window_days=7, current_window_hours=24,
                source_weights={"ygoprodeck_api": 1.0}, now=now,
            )

        delta, ctx = result[asset.id]
        assert delta is None and ctx.get("reason") == "no_baseline_data", (
            "NULL market_segment rows must be excluded — filter is not applying"
        )
