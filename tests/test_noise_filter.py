import backend.app.models  # noqa: F401
import asyncio
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.ingestion.pipeline import run_batch
from backend.app.ingestion.staging import repository as staging_repo
from backend.app.models.raw_listing import RawListing, RawListingStatus


def make_raw_listing(*, title: str) -> RawListing:
    return RawListing(
        id=uuid.uuid4(),
        source="ebay",
        source_listing_id=str(uuid.uuid4()),
        raw_title=title,
        price_usd=Decimal("19.99"),
        sold_at=datetime.now(UTC),
        currency_original="USD",
        url="https://example.com/listing",
        status=RawListingStatus.PENDING.value,
        failure_count=0,
    )


def _coerce_postgres_types_for_sqlite() -> None:
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


class NoiseFilterTests(TestCase):
    @patch("backend.app.ingestion.noise_filter.Anthropic")
    def test_filter_noise_parses_boolean_json_array(self, anthropic_cls):
        from backend.app.ingestion.noise_filter import filter_noise

        response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "[true, false, true]"
        response.content = [text_block]

        client = MagicMock()
        client.messages.create.return_value = response
        anthropic_cls.return_value = client

        result = filter_noise(
            [
                "Charizard ex 199/165 PSA 10",
                "Pokemon 50x bulk lot",
                "Pikachu 001/SV-P promo",
            ]
        )

        self.assertEqual(result, [True, False, True])
        anthropic_cls.assert_called_once_with()
        create_kwargs = client.messages.create.call_args.kwargs
        self.assertEqual(create_kwargs["model"], "claude-sonnet-4-6")
        self.assertEqual(
            create_kwargs["system"][0]["cache_control"],
            {"type": "ephemeral"},
        )
        self.assertEqual(create_kwargs["messages"][0]["role"], "user")
        self.assertIn("Pokemon 50x bulk lot", create_kwargs["messages"][0]["content"][0]["text"])

    @patch("backend.app.ingestion.noise_filter.logger")
    @patch("backend.app.ingestion.noise_filter.Anthropic")
    def test_filter_noise_returns_all_true_on_exception(self, anthropic_cls, logger):
        from backend.app.ingestion.noise_filter import filter_noise

        client = MagicMock()
        client.messages.create.side_effect = RuntimeError("boom")
        anthropic_cls.return_value = client

        result = filter_noise(["Pokemon 50x bulk lot", "booster box sealed"])

        self.assertEqual(result, [True, True])
        logger.warning.assert_called_once()


class StagingRepositoryNoiseFilterTests(TestCase):
    def test_mark_processed_sets_failed_status_for_noise_filtered_rows(self):
        with session_scope() as session:
            row = make_raw_listing(title="Pokemon 50x bulk lot")
            session.add(row)
            session.commit()

            staging_repo.mark_processed(session, row.id, None, Decimal("0"), "noise_filtered")
            session.commit()
            session.refresh(row)

        self.assertEqual(row.status, RawListingStatus.FAILED.value)
        self.assertEqual(row.error_reason, "noise_filtered")


class IngestionPipelineNoiseFilterTests(TestCase):
    def test_run_batch_marks_noise_and_stops_before_cache_lookup_when_all_rows_filtered(self):
        db = Mock()
        client = Mock()
        client.fetch_sold_listings = AsyncMock(return_value=[])
        pending_rows = [
            make_raw_listing(title="Pokemon 50x bulk lot"),
            make_raw_listing(title="ETB sealed product"),
        ]

        with (
            patch("backend.app.ingestion.pipeline._get_client", return_value=client),
            patch("backend.app.ingestion.pipeline.staging_repo.upsert_batch", return_value=0),
            patch("backend.app.ingestion.pipeline.staging_repo.load_pending", return_value=pending_rows),
            patch("backend.app.ingestion.noise_filter.filter_noise", return_value=[False, False]),
            patch("backend.app.ingestion.pipeline.staging_repo.mark_processed") as mark_processed_mock,
            patch("backend.app.ingestion.pipeline.mapping_cache.lookup_batch") as lookup_batch_mock,
        ):
            result = asyncio.run(run_batch(db))

        self.assertEqual(
            result.errors,
            [f"noise_filtered:{pending_rows[0].id}", f"noise_filtered:{pending_rows[1].id}"],
        )
        self.assertEqual(mark_processed_mock.call_count, 2)
        mark_processed_mock.assert_any_call(db, pending_rows[0].id, None, 0, "noise_filtered")
        mark_processed_mock.assert_any_call(db, pending_rows[1].id, None, 0, "noise_filtered")
        self.assertEqual(db.commit.call_count, 2)
        lookup_batch_mock.assert_not_called()
