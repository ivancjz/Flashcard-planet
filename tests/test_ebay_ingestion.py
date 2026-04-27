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


def make_browse_response(*, title: str, item_id: str, price: str, end_time: datetime) -> dict:
    """Build a Browse API JSON payload with a single itemSummary entry."""
    return {
        "itemSummaries": [
            {
                "itemId": item_id,
                "title": title,
                "itemEndDate": end_time.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                "price": {"value": price, "currency": "USD"},
            }
        ]
    }


def make_http_client(browse_data: dict) -> MagicMock:
    """Return a mock httpx.Client context manager.

    Behaviour:
    - client.post() simulates the OAuth token call (returns access_token).
    - client.get() simulates the Browse API search (returns browse_data as JSON).
    The Finding API call (also a GET) returns an empty XML body so
    _fetch_finding_completed falls back to Browse.
    """
    # OAuth token response (POST)
    token_response = MagicMock()
    token_response.raise_for_status.return_value = None
    token_response.json.return_value = {"access_token": "fake-token"}

    # Browse API response (GET)
    browse_response = MagicMock()
    browse_response.status_code = 200
    browse_response.text = ""  # no "10001" → Finding returns non-quota failure
    browse_response.raise_for_status.return_value = None
    browse_response.json.return_value = browse_data

    client = MagicMock()
    client.post.return_value = token_response
    client.get.return_value = browse_response

    client_context = MagicMock()
    client_context.__enter__.return_value = client
    client_context.__exit__.return_value = False
    return client_context


def create_asset(session: Session, *, name: str, external_id: str | None = None) -> Asset:
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
        external_id=external_id or f"asset:{name}",
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
        "ebay_cert_id": "test-ebay-cert-id",
        "ebay_search_keywords": "charizard",
        "ebay_sold_lookback_hours": 24,
    }
    defaults.update(overrides)
    return patch.multiple("backend.app.ingestion.ebay_sold.settings", **defaults)


# ── Patch Finding API to always return [] (empty) so Browse is the active path ──
_patch_finding = patch(
    "backend.app.ingestion.ebay_sold._fetch_finding_completed",
    return_value=[],
)


def test_ingest_returns_result_when_no_api_key() -> None:
    with session_scope() as session, patch_settings(ebay_app_id=""):
        result = ingest_ebay_sold_cards(session)

    assert result.cards_requested == 0


def test_price_inserted_for_matching_asset() -> None:
    with session_scope() as session:
        create_asset(session, name="Charizard")
        browse_data = make_browse_response(
            title="Charizard Base Set Holo Rare",
            item_id="ebay-item-001",
            price="450.00",
            end_time=datetime.now(UTC) - timedelta(hours=1),
        )

        with (
            patch_settings(),
            _patch_finding,
            patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=make_http_client(browse_data)),
        ):
            result = ingest_ebay_sold_cards(session)

        assert result.price_points_inserted == 1
        rows = session.scalars(select(PriceHistory).where(PriceHistory.source == EBAY_SOLD_PRICE_SOURCE)).all()
        assert len(rows) == 1
        assert rows[0].price == Decimal("450.00")


def test_duplicate_item_id_skipped() -> None:
    """Second ingest of the same eBay item_id is rejected by the item-ID dedup check."""
    with session_scope() as session:
        create_asset(session, name="Charizard")
        end_time = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
        browse_data = make_browse_response(
            title="Charizard Base Set Holo Rare",
            item_id="ebay-item-002",
            price="450.00",
            end_time=end_time,
        )

        http_client = make_http_client(browse_data)
        with (
            patch_settings(),
            _patch_finding,
            patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=http_client),
        ):
            # First ingest — inserts the price point.
            result1 = ingest_ebay_sold_cards(session)
            # Second ingest — same item_id → dedup check fires.
            result2 = ingest_ebay_sold_cards(session)

        assert result1.price_points_inserted == 1
        assert result2.price_points_inserted == 0
        assert result2.price_points_skipped_existing_timestamp == 1


def test_duplicate_timestamp_skipped() -> None:
    """Pre-existing PriceHistory row with the same (asset, source, captured_at) is skipped."""
    with session_scope() as session:
        asset = create_asset(session, name="Charizard")
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
        browse_data = make_browse_response(
            title="Charizard Base Set Holo Rare",
            item_id="ebay-item-003-no-log",  # no ObservationMatchLog row exists
            price="450.00",
            end_time=end_time,
        )

        with (
            patch_settings(),
            _patch_finding,
            patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=make_http_client(browse_data)),
        ):
            result = ingest_ebay_sold_cards(session)

        assert result.price_points_inserted == 0
        assert result.price_points_skipped_existing_timestamp == 1


def test_unmatched_title_is_skipped() -> None:
    with session_scope() as session:
        create_asset(session, name="Charizard")
        browse_data = make_browse_response(
            title="XYZ Random Item 12345 Completely Different",
            item_id="ebay-item-004",
            price="12.00",
            end_time=datetime.now(UTC) - timedelta(hours=1),
        )

        with (
            patch_settings(),
            _patch_finding,
            patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=make_http_client(browse_data)),
        ):
            result = ingest_ebay_sold_cards(session)

        assert result.price_points_inserted == 0
        assert result.observations_unmatched >= 1


def test_volume_signal_stored_in_metadata() -> None:
    with session_scope() as session:
        asset = create_asset(session, name="Charizard")
        browse_data = make_browse_response(
            title="Charizard Base Set Holo Rare",
            item_id="ebay-item-005",
            price="450.00",
            end_time=datetime.now(UTC) - timedelta(hours=1),
        )

        with (
            patch_settings(),
            _patch_finding,
            patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=make_http_client(browse_data)),
        ):
            ingest_ebay_sold_cards(session)

        refreshed_asset = session.scalar(select(Asset).where(Asset.id == asset.id))
        assert refreshed_asset is not None
        assert "ebay_sold_24h_count" in (refreshed_asset.metadata_json or {})


def test_api_calls_used_tracked() -> None:
    """api_calls_used in the result reflects the real HTTP calls made."""
    with session_scope() as session:
        create_asset(session, name="Charizard")
        browse_data = make_browse_response(
            title="Charizard Base Set Holo Rare",
            item_id="ebay-item-006",
            price="450.00",
            end_time=datetime.now(UTC) - timedelta(hours=1),
        )

        with (
            patch_settings(),
            _patch_finding,
            patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=make_http_client(browse_data)),
        ):
            result = ingest_ebay_sold_cards(session)

        # 1 OAuth call + 1 Finding attempt + 1 Browse fallback = 3 per asset
        assert result.api_calls_used >= 3


def test_future_dated_listing_is_skipped() -> None:
    """Listings with captured_at > now() must not be written to price_history.

    eBay returns future end_time for scheduled/upcoming auctions. Before the fix,
    these passed the lookback_cutoff filter and accumulated in the DB, eventually
    entering signal baseline windows as they aged into the past.
    """
    with session_scope() as session:
        create_asset(session, name="Charizard")
        future_end_time = datetime.now(UTC) + timedelta(days=9)
        browse_data = make_browse_response(
            title="Charizard Base Set Holo Rare",
            item_id="ebay-future-001",
            price="500.00",
            end_time=future_end_time,
        )

        with (
            patch_settings(),
            _patch_finding,
            patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=make_http_client(browse_data)),
        ):
            result = ingest_ebay_sold_cards(session)

        assert result.price_points_inserted == 0, (
            "future-dated listing must not be inserted into price_history"
        )
        rows = session.execute(select(PriceHistory)).scalars().all()
        assert len(rows) == 0


def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    for test in (
        test_ingest_returns_result_when_no_api_key,
        test_price_inserted_for_matching_asset,
        test_duplicate_item_id_skipped,
        test_duplicate_timestamp_skipped,
        test_unmatched_title_is_skipped,
        test_volume_signal_stored_in_metadata,
        test_api_calls_used_tracked,
        test_future_dated_listing_is_skipped,
    ):
        suite.addTest(unittest.FunctionTestCase(test))
    return suite
