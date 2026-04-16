from __future__ import annotations

import unittest
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401 — registers all models with Base.metadata
from backend.app.core.price_sources import POKEMON_TCG_PRICE_SOURCE, SAMPLE_PRICE_SOURCE
from backend.app.db.base import Base
from backend.app.models.asset import Asset
from backend.app.models.asset_signal import AssetSignal
from backend.app.models.observation_match_log import ObservationMatchLog
from backend.app.models.price_history import PriceHistory
from backend.app.services.card_detail_service import (
    CONFIDENCE_HIGH_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
    CONFIDENCE_MIN_SAMPLE_SIZE,
    CardDetailViewModel,
    _confidence_label,
    build_card_detail,
)


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


def make_asset(*, name: str = "Charizard", metadata_json: dict | None = None) -> Asset:
    return Asset(
        asset_class="TCG",
        category="Pokemon",
        name=name,
        set_name="Base Set",
        card_number="4",
        language="en",
        variant="Holo",
        metadata_json=metadata_json,
    )


def make_price_history(asset_id, *, price: str, days_ago: int = 0, source: str = POKEMON_TCG_PRICE_SOURCE) -> PriceHistory:
    return PriceHistory(
        asset_id=asset_id,
        price=Decimal(price),
        currency="USD",
        source=source,
        captured_at=datetime.now(UTC) - timedelta(days=days_ago),
    )


def make_observation(asset_id, *, confidence: str = "0.80", days_ago: int = 5) -> ObservationMatchLog:
    return ObservationMatchLog(
        provider=POKEMON_TCG_PRICE_SOURCE,
        external_item_id=str(uuid.uuid4()),
        matched_asset_id=asset_id,
        match_status="matched_existing",
        confidence=Decimal(confidence),
        requires_review=False,
        created_at=datetime.now(UTC) - timedelta(days=days_ago),
    )


class ConfidenceLabelTests(unittest.TestCase):
    def test_insufficient_data_when_sample_size_below_minimum(self):
        self.assertEqual(_confidence_label(Decimal("0.90"), CONFIDENCE_MIN_SAMPLE_SIZE - 1), "Insufficient data")

    def test_insufficient_data_when_avg_is_none(self):
        self.assertEqual(_confidence_label(None, CONFIDENCE_MIN_SAMPLE_SIZE + 1), "Insufficient data")

    def test_insufficient_data_when_both_zero_and_none(self):
        self.assertEqual(_confidence_label(None, 0), "Insufficient data")

    def test_high_when_avg_at_high_threshold(self):
        self.assertEqual(_confidence_label(CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MIN_SAMPLE_SIZE), "High")

    def test_high_when_avg_above_threshold(self):
        self.assertEqual(_confidence_label(Decimal("0.95"), 10), "High")

    def test_medium_when_avg_at_medium_threshold(self):
        self.assertEqual(_confidence_label(CONFIDENCE_MEDIUM_THRESHOLD, CONFIDENCE_MIN_SAMPLE_SIZE), "Medium")

    def test_medium_when_avg_between_thresholds(self):
        self.assertEqual(_confidence_label(Decimal("0.60"), 10), "Medium")

    def test_low_when_avg_below_medium_threshold(self):
        self.assertEqual(_confidence_label(Decimal("0.30"), 10), "Low")

    def test_low_when_avg_is_zero(self):
        self.assertEqual(_confidence_label(Decimal("0.00"), 10), "Low")


class BuildCardDetailTests(unittest.TestCase):
    def test_returns_none_for_nonexistent_asset(self):
        with session_scope() as db:
            result = build_card_detail(db, uuid.uuid4(), access_tier="free")
            self.assertIsNone(result)

    def test_returns_view_model_for_valid_asset(self):
        with session_scope() as db:
            asset = make_asset()
            db.add(asset)
            db.flush()
            db.add(make_price_history(asset.id, price="10.00"))
            db.flush()

            result = build_card_detail(db, asset.id, access_tier="free")

            self.assertIsInstance(result, CardDetailViewModel)
            self.assertEqual(result.name, "Charizard")
            self.assertEqual(result.currency, "USD")

    def test_free_tier_history_is_truncated(self):
        with session_scope() as db:
            asset = make_asset()
            db.add(asset)
            db.flush()
            # Add price history: one recent (2 days ago), one old (30 days ago)
            db.add(make_price_history(asset.id, price="10.00", days_ago=2))
            db.add(make_price_history(asset.id, price="8.00", days_ago=30))
            db.flush()

            result = build_card_detail(db, asset.id, access_tier="free")

            self.assertTrue(result.history_truncated)
            # Only the 2-day-ago point should be within the 7-day free window
            self.assertEqual(len(result.price_history), 1)
            self.assertEqual(result.price_history[0].price, Decimal("10.00"))

    def test_pro_tier_history_not_truncated(self):
        with session_scope() as db:
            asset = make_asset()
            db.add(asset)
            db.flush()
            db.add(make_price_history(asset.id, price="10.00", days_ago=2))
            db.add(make_price_history(asset.id, price="8.00", days_ago=30))
            db.flush()

            result = build_card_detail(db, asset.id, access_tier="pro")

            self.assertFalse(result.history_truncated)
            self.assertEqual(len(result.price_history), 2)

    def test_sample_size_zero_when_no_observations(self):
        with session_scope() as db:
            asset = make_asset()
            db.add(asset)
            db.flush()

            result = build_card_detail(db, asset.id, access_tier="free")

            self.assertEqual(result.sample_size, 0)

    def test_confidence_label_insufficient_when_no_observations(self):
        with session_scope() as db:
            asset = make_asset()
            db.add(asset)
            db.flush()

            result = build_card_detail(db, asset.id, access_tier="free")

            self.assertEqual(result.confidence_label, "Insufficient data")
            self.assertIsNone(result.match_confidence_avg)

    def test_sample_size_counts_matched_observations(self):
        with session_scope() as db:
            asset = make_asset()
            db.add(asset)
            db.flush()
            for _ in range(6):
                db.add(make_observation(asset.id, confidence="0.85"))
            db.flush()

            result = build_card_detail(db, asset.id, access_tier="free")

            self.assertEqual(result.sample_size, 6)
            self.assertEqual(result.confidence_label, "High")

    def test_source_breakdown_counts_by_source(self):
        with session_scope() as db:
            asset = make_asset()
            db.add(asset)
            db.flush()
            db.add(make_price_history(asset.id, price="10.00", days_ago=1, source=POKEMON_TCG_PRICE_SOURCE))
            db.add(make_price_history(asset.id, price="9.00", days_ago=2, source=POKEMON_TCG_PRICE_SOURCE))
            db.flush()

            result = build_card_detail(db, asset.id, access_tier="pro")

            self.assertEqual(result.source_breakdown.get(POKEMON_TCG_PRICE_SOURCE, 0), 2)

    def test_image_url_extracted_from_metadata_json(self):
        with session_scope() as db:
            asset = make_asset(metadata_json={"images": {"small": "https://example.com/card.png"}})
            db.add(asset)
            db.flush()

            result = build_card_detail(db, asset.id, access_tier="free")

            self.assertEqual(result.image_url, "https://example.com/card.png")

    def test_image_url_none_when_metadata_json_is_none(self):
        with session_scope() as db:
            asset = make_asset(metadata_json=None)
            db.add(asset)
            db.flush()

            result = build_card_detail(db, asset.id, access_tier="free")

            self.assertIsNone(result.image_url)

    def test_percent_change_computed_from_two_price_points(self):
        with session_scope() as db:
            asset = make_asset()
            db.add(asset)
            db.flush()
            # Latest: 12.00, Previous: 10.00 → +20%
            db.add(make_price_history(asset.id, price="12.00", days_ago=1))
            db.add(make_price_history(asset.id, price="10.00", days_ago=2))
            db.flush()

            result = build_card_detail(db, asset.id, access_tier="pro")

            self.assertEqual(result.latest_price, Decimal("12.00"))
            self.assertEqual(result.previous_price, Decimal("10.00"))
            self.assertEqual(result.percent_change, Decimal("20.00"))
