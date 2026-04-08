from __future__ import annotations

import unittest
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from sqlalchemy import JSON, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
from backend.app.db.base import Base
from backend.app.ingestion.ebay_sold import EBAY_SOLD_PRICE_SOURCE, ingest_ebay_sold_cards
from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory


def _coerce_postgres_types_for_sqlite() -> None:
    # Only convert JSONB → JSON; SQLAlchemy's UUID type handles SQLite natively via CHAR(32).
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()


@contextmanager
def session_scope() -> Session:
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


def make_xml_response(*, title: str, price: str, end_time: datetime) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<findCompletedItemsResponse xmlns="urn:ebay:apis:eBLBaseComponents">
  <ack>Success</ack>
  <searchResult count="1">
    <item>
      <title>{title}</title>
      <listingInfo>
        <endTime>{end_time.astimezone(UTC).isoformat().replace("+00:00", "Z")}</endTime>
      </listingInfo>
      <sellingStatus>
        <convertedCurrentPrice currencyId="USD">{price}</convertedCurrentPrice>
      </sellingStatus>
    </item>
  </searchResult>
</findCompletedItemsResponse>
"""


def make_http_client(xml_payload: str) -> MagicMock:
    response = MagicMock()
    response.text = xml_payload
    response.raise_for_status.return_value = None
    client = MagicMock()
    client.get.return_value = response
    client_context = MagicMock()
    client_context.__enter__.return_value = client
    client_context.__exit__.return_value = False
    return client_context


def create_asset(session: Session, *, name: str) -> Asset:
    asset = Asset(
        asset_class="TCG",
        category="Pokemon",
        name=name,
        set_name="Base Set",
        card_number="4",
        year=1999,
        language="EN",
        variant="Holo",
        grade_company=None,
        grade_score=None,
        external_id=f"asset:{name}",
        metadata_json={},
        notes="Test asset.",
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


def patch_settings(**overrides: object):
    defaults = {
        "ebay_app_id": "test-ebay-app-id",
        "ebay_search_keywords": "charizard",
        "ebay_sold_lookback_hours": 24,
    }
    defaults.update(overrides)
    return patch.multiple("backend.app.ingestion.ebay_sold.settings", **defaults)


def test_ingest_returns_result_when_no_api_key() -> None:
    with session_scope() as session, patch_settings(ebay_app_id=""):
        result = ingest_ebay_sold_cards(session)

    assert result.cards_requested == 0


def test_price_inserted_for_matching_asset() -> None:
    with session_scope() as session:
        create_asset(session, name="Charizard Base Set Holo")
        xml_payload = make_xml_response(
            title="Charizard Base Set Holo PSA 9",
            price="450.00",
            end_time=datetime.now(UTC) - timedelta(hours=1),
        )

        with patch_settings(), patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=make_http_client(xml_payload)):
            result = ingest_ebay_sold_cards(session)

        assert result.price_points_inserted == 1
        rows = session.scalars(select(PriceHistory).where(PriceHistory.source == EBAY_SOLD_PRICE_SOURCE)).all()
        assert len(rows) == 1
        assert rows[0].price == Decimal("450.00")


def test_duplicate_timestamp_skipped() -> None:
    with session_scope() as session:
        asset = create_asset(session, name="Charizard Base Set Holo")
        end_time = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
        session.add(
            PriceHistory(
                asset_id=asset.id,
                source=EBAY_SOLD_PRICE_SOURCE,
                currency="USD",
                price=Decimal("450.00"),
                captured_at=end_time,
            )
        )
        session.commit()
        xml_payload = make_xml_response(
            title="Charizard Base Set Holo PSA 9",
            price="450.00",
            end_time=end_time,
        )

        with patch_settings(), patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=make_http_client(xml_payload)):
            result = ingest_ebay_sold_cards(session)

        assert result.price_points_inserted == 0
        assert result.price_points_skipped_existing_timestamp == 1


def test_unmatched_title_is_skipped() -> None:
    with session_scope() as session:
        create_asset(session, name="Charizard Base Set Holo")
        xml_payload = make_xml_response(
            title="XYZ Random Item 12345 Completely Different",
            price="12.00",
            end_time=datetime.now(UTC) - timedelta(hours=1),
        )

        with patch_settings(), patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=make_http_client(xml_payload)):
            result = ingest_ebay_sold_cards(session)

        assert result.price_points_inserted == 0
        assert result.observations_unmatched >= 1


def test_volume_signal_stored_in_metadata() -> None:
    with session_scope() as session:
        asset = create_asset(session, name="Charizard Base Set Holo")
        xml_payload = make_xml_response(
            title="Charizard Base Set Holo PSA 9",
            price="450.00",
            end_time=datetime.now(UTC) - timedelta(hours=1),
        )

        with patch_settings(), patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=make_http_client(xml_payload)):
            ingest_ebay_sold_cards(session)

        refreshed_asset = session.scalar(select(Asset).where(Asset.id == asset.id))
        assert refreshed_asset is not None
        assert "ebay_sold_24h_count" in (refreshed_asset.metadata_json or {})


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    for test in (
        test_ingest_returns_result_when_no_api_key,
        test_price_inserted_for_matching_asset,
        test_duplicate_timestamp_skipped,
        test_unmatched_title_is_skipped,
        test_volume_signal_stored_in_metadata,
    ):
        suite.addTest(unittest.FunctionTestCase(test))
    return suite
