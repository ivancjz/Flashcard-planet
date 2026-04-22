"""Tests for eBay scheduled ingestion — covers spec areas:

Config / cron validation  · Budget logic  · Asset ordering
Dedup (item_id + timestamp) · Failure isolation · Summary completeness
"""
from __future__ import annotations

import unittest
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from sqlalchemy import JSON, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401
from backend.app.backstage.scheduler import (
    EbayScheduledRunSummary,
    _register_ebay_job,
    _run_ebay_ingestion,
)
from backend.app.db.base import Base
from backend.app.ingestion.ebay_sold import EBAY_SOLD_PRICE_SOURCE, ingest_ebay_sold_cards
from backend.app.models.asset import Asset
from backend.app.models.observation_match_log import ObservationMatchLog
from backend.app.models.price_history import PriceHistory


# ── DB helpers ────────────────────────────────────────────────────────────────

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


def make_asset(
    session: Session,
    *,
    name: str,
    external_id: str,
    last_ingested_at: str | None = None,
) -> Asset:
    asset = Asset(
        asset_class="TCG",
        category="Pokemon",
        name=name,
        set_name="Base Set",
        card_number="1",
        year=1999,
        language="EN",
        variant="Holo",
        grade_company=None,
        grade_score=None,
        external_id=external_id,
        metadata_json={"ebay_sold_last_ingested_at": last_ingested_at} if last_ingested_at else {},
        notes="",
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


def make_browse_response(*, title: str, item_id: str, price: str, end_time: datetime) -> dict:
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
    token_response = MagicMock()
    token_response.raise_for_status.return_value = None
    token_response.json.return_value = {"access_token": "fake-token"}

    browse_response = MagicMock()
    browse_response.status_code = 200
    browse_response.text = ""
    browse_response.raise_for_status.return_value = None
    browse_response.json.return_value = browse_data

    client = MagicMock()
    client.post.return_value = token_response
    client.get.return_value = browse_response

    ctx = MagicMock()
    ctx.__enter__.return_value = client
    ctx.__exit__.return_value = False
    return ctx


def patch_ebay_settings(**overrides: object):
    defaults = {
        "ebay_app_id": "test-app-id",
        "ebay_cert_id": "test-cert-id",
        "ebay_sold_lookback_hours": 24,
        "ebay_search_keywords": "charizard",
    }
    defaults.update(overrides)
    return patch.multiple("backend.app.ingestion.ebay_sold.settings", **defaults)


_patch_finding = patch(
    "backend.app.ingestion.ebay_sold._fetch_finding_completed",
    return_value=[],
)


# ── Config / registration ────────────────────────────────────────────────────

def test_register_ebay_job_uses_interval_trigger() -> None:
    """Job must be registered with an interval trigger, not a cron trigger."""
    scheduler = MagicMock()
    settings = MagicMock()
    settings.ebay_scheduled_ingest_enabled = True
    settings.ebay_app_id = "app-id"
    settings.ebay_cert_id = "cert-id"

    _register_ebay_job(scheduler, settings)

    scheduler.add_job.assert_called_once()
    call_args = scheduler.add_job.call_args
    assert call_args[0][1] == "interval", "trigger must be interval, not cron"
    assert call_args[1]["hours"] == 24
    assert call_args[1]["next_run_time"] is None  # paused until prepare_scheduler_for_startup


def test_register_ebay_job_disabled_not_registered() -> None:
    """When the feature is disabled the job must not be added."""
    scheduler = MagicMock()
    settings = MagicMock()
    settings.ebay_scheduled_ingest_enabled = False

    _register_ebay_job(scheduler, settings)

    scheduler.add_job.assert_not_called()


def test_register_ebay_job_missing_credentials_not_registered() -> None:
    """Enabled but missing credentials — job must not be added."""
    scheduler = MagicMock()
    settings = MagicMock()
    settings.ebay_scheduled_ingest_enabled = True
    settings.ebay_app_id = ""
    settings.ebay_cert_id = ""

    _register_ebay_job(scheduler, settings)

    scheduler.add_job.assert_not_called()


def test_register_ebay_job_valid_registers() -> None:
    """Valid config must register exactly one job with the correct id."""
    scheduler = MagicMock()
    settings = MagicMock()
    settings.ebay_scheduled_ingest_enabled = True
    settings.ebay_app_id = "app-id"
    settings.ebay_cert_id = "cert-id"

    _register_ebay_job(scheduler, settings)

    scheduler.add_job.assert_called_once()
    call_kwargs = scheduler.add_job.call_args[1]
    assert call_kwargs["id"] == "ebay-ingestion"


# ── Budget logic ──────────────────────────────────────────────────────────────

def test_run_ebay_ingestion_skipped_when_disabled() -> None:
    """_run_ebay_ingestion returns 'skipped' summary when feature is disabled."""
    settings_patch = patch(
        "backend.app.backstage.scheduler.get_settings",
        return_value=MagicMock(
            ebay_scheduled_ingest_enabled=False,
            ebay_app_id="app-id",
            ebay_cert_id="cert-id",
        ),
    )
    with settings_patch:
        summary = _run_ebay_ingestion()

    assert isinstance(summary, EbayScheduledRunSummary)
    assert summary.run_status == "skipped"
    assert summary.job_blocked_reason == "disabled"


def test_run_ebay_ingestion_skipped_missing_credentials() -> None:
    settings_patch = patch(
        "backend.app.backstage.scheduler.get_settings",
        return_value=MagicMock(
            ebay_scheduled_ingest_enabled=True,
            ebay_app_id="",
            ebay_cert_id="",
        ),
    )
    with settings_patch:
        summary = _run_ebay_ingestion()

    assert summary.run_status == "skipped"
    assert summary.job_blocked_reason == "missing_credentials"


def test_budget_exhausted_returns_skipped() -> None:
    """When all daily budget is consumed the run returns 'skipped'."""
    today_iso = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    with session_scope() as session:
        # Create 2 assets already ingested today.
        make_asset(session, name="Card A", external_id="ext-a", last_ingested_at=today_iso)
        make_asset(session, name="Card B", external_id="ext-b", last_ingested_at=today_iso)

        mock_settings = MagicMock(
            ebay_scheduled_ingest_enabled=True,
            ebay_app_id="app-id",
            ebay_cert_id="cert-id",
            ebay_daily_budget_limit=2,    # 2 assets already done today
            ebay_max_calls_per_run=10,
        )
        settings_patch = patch("backend.app.backstage.scheduler.get_settings", return_value=mock_settings)
        session_patch = patch(
            "backend.app.backstage.scheduler.SessionLocal",
            return_value=_make_session_ctx(session),
        )
        pools_patch = patch(
            "backend.app.backstage.scheduler.get_tracked_pokemon_pools",
            return_value=[],
        )

        with settings_patch, session_patch, pools_patch:
            summary = _run_ebay_ingestion()

    assert summary.run_status == "skipped"
    assert summary.job_blocked_reason == "daily_budget_exhausted"
    assert summary.budget_remaining == 0


def test_budget_cap_limits_assets_processed() -> None:
    """effective_limit = min(max_calls_per_run, remaining_budget) — only that many assets queried."""
    today_iso = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end_time = datetime.now(UTC) - timedelta(hours=1)

    with session_scope() as session:
        # 5 assets in DB; only 2 already ingested today → remaining_daily_budget = 3
        make_asset(session, name="Card A", external_id="ext-a", last_ingested_at=today_iso)
        make_asset(session, name="Card B", external_id="ext-b", last_ingested_at=today_iso)
        make_asset(session, name="Charizard", external_id="ext-c")
        make_asset(session, name="Pikachu", external_id="ext-d")
        make_asset(session, name="Mewtwo", external_id="ext-e")

        mock_settings = MagicMock(
            ebay_scheduled_ingest_enabled=True,
            ebay_app_id="app-id",
            ebay_cert_id="cert-id",
            ebay_daily_budget_limit=5,    # 5 total → 3 remaining
            ebay_max_calls_per_run=2,     # capped to 2
        )
        captured: list[list[str]] = []

        def _fake_ingest(session, card_ids=None, **kwargs):
            captured.append(list(card_ids or []))
            from backend.app.ingestion.pokemon_tcg import IngestionResult
            return IngestionResult(cards_requested=len(card_ids or []), cards_processed=len(card_ids or []))

        settings_patch = patch("backend.app.backstage.scheduler.get_settings", return_value=mock_settings)
        session_patch = patch("backend.app.backstage.scheduler.SessionLocal", return_value=_make_session_ctx(session))
        pools_patch = patch("backend.app.backstage.scheduler.get_tracked_pokemon_pools", return_value=[])
        ingest_patch = patch("backend.app.ingestion.ebay_sold.ingest_ebay_sold_cards", side_effect=_fake_ingest)

        with settings_patch, session_patch, pools_patch, ingest_patch:
            summary = _run_ebay_ingestion()

    assert len(captured) == 1
    assert len(captured[0]) == 2  # min(max_calls_per_run=2, remaining=3) = 2
    assert summary.assets_skipped_budget >= 1


# ── Asset ordering ────────────────────────────────────────────────────────────

def test_priority_ordering_tracked_pool_first() -> None:
    """Tracked-pool assets appear before untracked assets in selected_ids."""
    today_iso = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    with session_scope() as session:
        # ext-untracked ingested recently; ext-tracked never ingested but NOT in priority pool
        # ext-priority is the tracked-pool card → must come first regardless of last_ingested_at
        make_asset(session, name="Untracked Card", external_id="ext-untracked", last_ingested_at=None)
        make_asset(session, name="Priority Card", external_id="ext-priority", last_ingested_at=None)

        mock_settings = MagicMock(
            ebay_scheduled_ingest_enabled=True,
            ebay_app_id="app-id",
            ebay_cert_id="cert-id",
            ebay_daily_budget_limit=100,
            ebay_max_calls_per_run=10,
        )

        tracked_pool = MagicMock()
        tracked_pool.card_ids = ["ext-priority"]

        captured: list[list[str]] = []

        def _fake_ingest(session, card_ids=None, **kwargs):
            captured.append(list(card_ids or []))
            from backend.app.ingestion.pokemon_tcg import IngestionResult
            return IngestionResult(cards_requested=len(card_ids or []), cards_processed=len(card_ids or []))

        settings_patch = patch("backend.app.backstage.scheduler.get_settings", return_value=mock_settings)
        session_patch = patch("backend.app.backstage.scheduler.SessionLocal", return_value=_make_session_ctx(session))
        pools_patch = patch("backend.app.backstage.scheduler.get_tracked_pokemon_pools", return_value=[tracked_pool])
        ingest_patch = patch("backend.app.ingestion.ebay_sold.ingest_ebay_sold_cards", side_effect=_fake_ingest)

        with settings_patch, session_patch, pools_patch, ingest_patch:
            _run_ebay_ingestion()

    assert captured
    ids = captured[0]
    assert ids.index("ext-priority") < ids.index("ext-untracked")


def test_least_recently_ingested_comes_first_within_tier() -> None:
    """Within the same priority tier (both untracked) the oldest ingestion comes first."""
    old_time = (datetime.now(UTC) - timedelta(days=5)).isoformat()
    new_time = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    with session_scope() as session:
        make_asset(session, name="New Card", external_id="ext-new", last_ingested_at=new_time)
        make_asset(session, name="Old Card", external_id="ext-old", last_ingested_at=old_time)

        mock_settings = MagicMock(
            ebay_scheduled_ingest_enabled=True,
            ebay_app_id="app-id",
            ebay_cert_id="cert-id",
            ebay_daily_budget_limit=100,
            ebay_max_calls_per_run=2,
        )

        captured: list[list[str]] = []

        def _fake_ingest(session, card_ids=None, **kwargs):
            captured.append(list(card_ids or []))
            from backend.app.ingestion.pokemon_tcg import IngestionResult
            return IngestionResult(cards_requested=len(card_ids or []), cards_processed=len(card_ids or []))

        settings_patch = patch("backend.app.backstage.scheduler.get_settings", return_value=mock_settings)
        session_patch = patch("backend.app.backstage.scheduler.SessionLocal", return_value=_make_session_ctx(session))
        pools_patch = patch("backend.app.backstage.scheduler.get_tracked_pokemon_pools", return_value=[])
        ingest_patch = patch("backend.app.ingestion.ebay_sold.ingest_ebay_sold_cards", side_effect=_fake_ingest)

        with settings_patch, session_patch, pools_patch, ingest_patch:
            _run_ebay_ingestion()

    assert captured
    ids = captured[0]
    assert ids.index("ext-old") < ids.index("ext-new")


# ── Dedup: item_id ────────────────────────────────────────────────────────────

def test_item_id_dedup_prevents_duplicate_price_point() -> None:
    """An eBay item_id already in ObservationMatchLog must not produce a second PriceHistory row."""
    with session_scope() as session:
        asset = make_asset(session, name="Charizard", external_id="ext-charizard")
        end_time = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
        browse_data = make_browse_response(
            title="Charizard Base Set Holo Rare",
            item_id="ebay-dup-item-id",
            price="400.00",
            end_time=end_time,
        )

        with (
            patch_ebay_settings(),
            _patch_finding,
            patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=make_http_client(browse_data)),
        ):
            r1 = ingest_ebay_sold_cards(session)
            r2 = ingest_ebay_sold_cards(session)

        assert r1.price_points_inserted == 1
        assert r2.price_points_inserted == 0
        assert r2.price_points_skipped_existing_timestamp >= 1
        assert "duplicates_skipped_item_id" in r2.observation_match_status_counts


def test_timestamp_dedup_fires_when_no_observation_log() -> None:
    """When no ObservationMatchLog exists, the (asset, source, captured_at) tuple dedup fires."""
    with session_scope() as session:
        asset = make_asset(session, name="Charizard", external_id="ext-charizard2")
        end_time = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=2)
        # Pre-seed PriceHistory without an ObservationMatchLog entry.
        session.add(
            PriceHistory(
                asset_id=asset.id,
                source=EBAY_SOLD_PRICE_SOURCE,
                currency="USD",
                price=Decimal("400.00"),
                captured_at=end_time,
            )
        )
        session.commit()
        browse_data = make_browse_response(
            title="Charizard Base Set Holo Rare",
            item_id="never-seen-item",
            price="400.00",
            end_time=end_time,
        )

        with (
            patch_ebay_settings(),
            _patch_finding,
            patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=make_http_client(browse_data)),
        ):
            result = ingest_ebay_sold_cards(session)

        assert result.price_points_inserted == 0
        assert result.price_points_skipped_existing_timestamp >= 1
        assert "duplicates_skipped_timestamp" in result.observation_match_status_counts


# ── Failure isolation ─────────────────────────────────────────────────────────

def test_ingest_exception_returns_failed_summary() -> None:
    """If SessionLocal raises during ingestion work, _run_ebay_ingestion returns run_status='failed'.

    Call 1 (start_run) succeeds; call 2 (inner work session) raises; call 3 (finish_run/prune) succeeds.
    """
    mock_settings = MagicMock(
        ebay_scheduled_ingest_enabled=True,
        ebay_app_id="app-id",
        ebay_cert_id="cert-id",
        ebay_daily_budget_limit=100,
        ebay_max_calls_per_run=10,
    )

    _call_n: list[int] = [0]

    def _sl_factory():
        _call_n[0] += 1
        if _call_n[0] == 2:
            raise RuntimeError("DB down")
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=MagicMock())
        ctx.__exit__ = MagicMock(return_value=False)
        return ctx

    settings_patch = patch("backend.app.backstage.scheduler.get_settings", return_value=mock_settings)
    session_patch = patch("backend.app.backstage.scheduler.SessionLocal", side_effect=_sl_factory)
    pools_patch = patch("backend.app.backstage.scheduler.get_tracked_pokemon_pools", return_value=[])

    with settings_patch, session_patch, pools_patch:
        summary = _run_ebay_ingestion()

    assert summary.run_status == "failed"
    assert summary.job_blocked_reason == "exception"


def test_asset_failure_does_not_abort_others() -> None:
    """When one asset's Browse API call fails, other assets still get processed."""
    with session_scope() as session:
        make_asset(session, name="Charizard", external_id="ext-char")
        make_asset(session, name="Pikachu", external_id="ext-pika")

        call_count = [0]

        def _fake_get(*args, **kwargs):
            call_count[0] += 1
            resp = MagicMock()
            resp.status_code = 200
            resp.text = ""
            resp.raise_for_status.return_value = None
            if call_count[0] == 1:
                # First asset: raise exception
                resp.raise_for_status.side_effect = RuntimeError("network blip")
            else:
                resp.json.return_value = make_browse_response(
                    title="Pikachu Base Set Holo",
                    item_id="ebay-pika-001",
                    price="50.00",
                    end_time=datetime.now(UTC) - timedelta(hours=1),
                )
            return resp

        token_response = MagicMock()
        token_response.raise_for_status.return_value = None
        token_response.json.return_value = {"access_token": "fake-token"}

        client = MagicMock()
        client.post.return_value = token_response
        client.get.side_effect = _fake_get

        ctx = MagicMock()
        ctx.__enter__.return_value = client
        ctx.__exit__.return_value = False

        with (
            patch_ebay_settings(),
            _patch_finding,
            patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=ctx),
        ):
            result = ingest_ebay_sold_cards(session)

        # The failed asset should NOT abort the second one.
        assert result.cards_failed >= 1
        # At least one of Charizard/Pikachu was attempted.
        assert result.cards_requested == 2


# ── Summary completeness ──────────────────────────────────────────────────────

def test_summary_fields_all_present() -> None:
    """EbayScheduledRunSummary must expose every field required by the spec."""
    summary = EbayScheduledRunSummary(run_status="success")
    required_fields = [
        "run_status", "assets_considered", "assets_processed", "assets_skipped_budget",
        "errors", "api_calls_used", "budget_remaining", "observations_fetched",
        "matched", "unmatched", "price_points_inserted", "duplicates_skipped",
        "match_status_counts", "job_blocked_reason",
    ]
    for field_name in required_fields:
        assert hasattr(summary, field_name), f"Missing field: {field_name}"


def test_summary_populated_on_successful_run() -> None:
    """After a successful run the summary should carry non-trivial metrics."""
    with session_scope() as session:
        make_asset(session, name="Charizard", external_id="ext-char")
        browse_data = make_browse_response(
            title="Charizard Base Set Holo Rare",
            item_id="ebay-summary-item",
            price="450.00",
            end_time=datetime.now(UTC) - timedelta(hours=1),
        )

        mock_settings = MagicMock(
            ebay_scheduled_ingest_enabled=True,
            ebay_app_id="app-id",
            ebay_cert_id="cert-id",
            ebay_daily_budget_limit=100,
            ebay_max_calls_per_run=10,
        )

        settings_patch = patch("backend.app.backstage.scheduler.get_settings", return_value=mock_settings)
        session_patch = patch("backend.app.backstage.scheduler.SessionLocal", return_value=_make_session_ctx(session))
        pools_patch = patch("backend.app.backstage.scheduler.get_tracked_pokemon_pools", return_value=[])
        http_patch = patch(
            "backend.app.ingestion.ebay_sold.httpx.Client",
            return_value=make_http_client(browse_data),
        )
        ebay_settings_patch = patch_ebay_settings()

        with settings_patch, session_patch, pools_patch, http_patch, _patch_finding, ebay_settings_patch:
            summary = _run_ebay_ingestion()

    assert summary.run_status in ("success", "partial")
    assert summary.assets_considered >= 1
    assert summary.assets_processed >= 1
    assert summary.api_calls_used >= 1
    assert summary.price_points_inserted >= 1
    assert summary.job_blocked_reason is None


# ── Helper ────────────────────────────────────────────────────────────────────

def _make_session_ctx(session: Session) -> MagicMock:
    """Wrap an existing Session in a context-manager mock for SessionLocal()."""
    ctx = MagicMock()
    ctx.__enter__.return_value = session
    ctx.__exit__.return_value = False
    return ctx


# ── Test runner ───────────────────────────────────────────────────────────────

def load_tests(loader: unittest.TestLoader, tests: unittest.TestSuite, pattern: str | None) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    for test in (
        test_register_ebay_job_invalid_cron_not_registered,
        test_register_ebay_job_disabled_not_registered,
        test_register_ebay_job_missing_credentials_not_registered,
        test_register_ebay_job_valid_registers,
        test_run_ebay_ingestion_skipped_when_disabled,
        test_run_ebay_ingestion_skipped_missing_credentials,
        test_budget_exhausted_returns_skipped,
        test_budget_cap_limits_assets_processed,
        test_priority_ordering_tracked_pool_first,
        test_least_recently_ingested_comes_first_within_tier,
        test_item_id_dedup_prevents_duplicate_price_point,
        test_timestamp_dedup_fires_when_no_observation_log,
        test_ingest_exception_returns_failed_summary,
        test_asset_failure_does_not_abort_others,
        test_summary_fields_all_present,
        test_summary_populated_on_successful_run,
    ):
        suite.addTest(unittest.FunctionTestCase(test))
    return suite
