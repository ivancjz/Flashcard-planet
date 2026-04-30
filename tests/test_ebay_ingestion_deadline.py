"""TDD tests for wall-clock deadline in ebay-ingestion.

All three tests are written RED-first; they will fail until the production
code adds `deadline` param to `ingest_ebay_sold_cards` and
`deadline_reached` / `assets_remaining` fields to `IngestionResult` and
`EbayScheduledRunSummary`.
"""
from __future__ import annotations

import unittest
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
from backend.app.db.base import Base
from backend.app.ingestion.ebay_sold import ingest_ebay_sold_cards
from backend.app.models.asset import Asset


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
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with SessionLocal() as db_session:
        yield db_session
    Base.metadata.drop_all(engine)


def _make_asset(session: Session, *, name: str, n: int) -> Asset:
    asset = Asset(
        asset_class="TCG",
        category="Pokemon",
        name=f"{name}-{n}",
        set_name="Base Set",
        card_number=str(n),
        year=1999,
        language="EN",
        variant="Holo",
        grade_company=None,
        grade_score=None,
        external_id=f"ext-{name}-{n}",
        metadata_json={},
        notes="",
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


def _patch_settings(**overrides: object):
    defaults = {
        "ebay_app_id": "test-app-id",
        "ebay_cert_id": "test-cert-id",
        "ebay_search_keywords": "charizard",
        "ebay_sold_lookback_hours": 24,
    }
    defaults.update(overrides)
    return patch.multiple("backend.app.ingestion.ebay_sold.settings", **defaults)


def _make_http_client_stub() -> MagicMock:
    """Minimal HTTP stub: OAuth succeeds, Browse returns empty itemSummaries."""
    token_resp = MagicMock()
    token_resp.raise_for_status.return_value = None
    token_resp.json.return_value = {"access_token": "fake-token"}

    browse_resp = MagicMock()
    browse_resp.status_code = 200
    browse_resp.text = ""
    browse_resp.raise_for_status.return_value = None
    browse_resp.json.return_value = {"itemSummaries": []}

    client = MagicMock()
    client.post.return_value = token_resp
    client.get.return_value = browse_resp

    ctx = MagicMock()
    ctx.__enter__.return_value = client
    ctx.__exit__.return_value = False
    return ctx


_patch_finding = patch(
    "backend.app.ingestion.ebay_sold._fetch_finding_completed",
    return_value=[],
)


class DeadlineTriggerTests(unittest.TestCase):

    def test_deadline_triggers_break(self):
        """Passing a deadline already in the past aborts the loop immediately,
        sets deadline_reached=True and assets_remaining == total assets."""
        with session_scope() as session:
            for i in range(5):
                _make_asset(session, name="Card", n=i)

            past_deadline = datetime.now(UTC) - timedelta(seconds=1)

            with (
                _patch_settings(),
                _patch_finding,
                patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=_make_http_client_stub()),
            ):
                result = ingest_ebay_sold_cards(
                    session,
                    deadline=past_deadline,
                )

        self.assertTrue(result.deadline_reached)
        self.assertGreater(result.assets_remaining, 0)

    def test_deadline_not_triggered_on_normal_run(self):
        """A far-future deadline never fires; all assets attempted, deadline_reached stays False."""
        with session_scope() as session:
            for i in range(3):
                _make_asset(session, name="Card", n=i)

            far_future = datetime.now(UTC) + timedelta(hours=1)

            with (
                _patch_settings(),
                _patch_finding,
                patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=_make_http_client_stub()),
            ):
                result = ingest_ebay_sold_cards(
                    session,
                    deadline=far_future,
                )

        self.assertFalse(result.deadline_reached)
        self.assertEqual(result.assets_remaining, 0)
        self.assertEqual(result.cards_processed, 3)

    def test_meta_json_carries_deadline_flag(self):
        """When deadline fires, scheduler meta_json contains deadline_reached: True
        and assets_remaining as a positive int."""
        from backend.app.backstage.scheduler import (
            EbayScheduledRunSummary,
            JOB_WALL_CLOCK_LIMIT,
            _run_ebay_ingestion,
        )

        # Patch the deadline to be 0 seconds so it fires immediately
        zero_limit = timedelta(seconds=0)

        with (
            patch("backend.app.backstage.scheduler.JOB_WALL_CLOCK_LIMIT", zero_limit),
            patch("backend.app.backstage.scheduler.SessionLocal") as mock_session_local,
            patch("backend.app.backstage.scheduler.get_settings") as mock_settings,
            patch("backend.app.backstage.scheduler.start_run", return_value="run-id-1"),
            patch("backend.app.backstage.scheduler.finish_run") as mock_finish_run,
            patch("backend.app.backstage.scheduler.prune_old_runs"),
            patch("backend.app.backstage.scheduler.get_tracked_pokemon_pools", return_value=[]),
            patch("backend.app.ingestion.ebay_sold._fetch_finding_completed", return_value=[]),
            patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=_make_http_client_stub()),
        ):
            settings = MagicMock()
            settings.ebay_scheduled_ingest_enabled = True
            settings.ebay_app_id = "test-app"
            settings.ebay_cert_id = "test-cert"
            settings.ebay_daily_budget_limit = 100
            settings.ebay_max_calls_per_run = 50
            mock_settings.return_value = settings

            # Build a fake DB session with 3 assets
            asset1 = MagicMock(spec=Asset)
            asset1.id = "a1"
            asset1.external_id = "ext-1"
            asset1.metadata_json = {}
            asset2 = MagicMock(spec=Asset)
            asset2.id = "a2"
            asset2.external_id = "ext-2"
            asset2.metadata_json = {}
            asset3 = MagicMock(spec=Asset)
            asset3.id = "a3"
            asset3.external_id = "ext-3"
            asset3.metadata_json = {}
            all_assets = [asset1, asset2, asset3]

            fake_session = MagicMock()
            fake_session.scalars.return_value.all.return_value = all_assets
            session_ctx = MagicMock()
            session_ctx.__enter__.return_value = fake_session
            session_ctx.__exit__.return_value = False
            mock_session_local.return_value = session_ctx

            _run_ebay_ingestion()

        # finish_run should have been called with meta_json containing deadline info
        call_kwargs = mock_finish_run.call_args.kwargs
        meta = call_kwargs.get("meta_json") or {}
        self.assertIn("deadline_reached", meta)
        self.assertTrue(meta["deadline_reached"])
        self.assertIn("assets_remaining", meta)
        self.assertIsInstance(meta["assets_remaining"], int)
        self.assertGreater(meta["assets_remaining"], 0)
