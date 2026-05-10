"""
tests/test_graded_shadow_admission.py

TDD tests for Phase 0 Graded Shadow Admission.

Covers:
  1. Graded title creates audit row when flag enabled
  2. Graded title skipped entirely when flag disabled
  3. Raw listing unaffected by shadow path
  4. Duplicate audit rows are idempotent (ON CONFLICT DO NOTHING)
  5. shadow_decision buckets assigned correctly (parametrized)
  6. Compatibility gate failure → no audit row
  7. Label endpoint updates a row
  8. Label endpoint rejects invalid label
  9. Diag endpoint precision summary matches pre-populated data
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import JSON, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401 — register all models with Base
from backend.app.api.deps import get_database
from backend.app.backstage.routes import router as backstage_router
from backend.app.db.base import Base
from backend.app.ingestion.ebay_sold import EBAY_SOLD_PRICE_SOURCE, ingest_ebay_sold_cards
from backend.app.models.asset import Asset
from backend.app.models.graded_observation_audit import GradedObservationAudit  # noqa: imported for side-effect
from backend.app.models.observation_match_log import ObservationMatchLog
from backend.app.models.price_history import PriceHistory


# ── SQLite in-memory session ──────────────────────────────────────────────────

def _coerce_postgres_types() -> None:
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()


@contextmanager
def session_scope() -> Session:
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


# ── Shared test helpers ───────────────────────────────────────────────────────

def _create_asset(db: Session, *, name: str = "Charizard") -> Asset:
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
        external_id=f"asset:{name}:{uuid.uuid4()}",
        metadata_json={},
        notes="test",
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def _browse_response(*, title: str, item_id: str, price: str = "45.00") -> dict:
    end_time = datetime.now(UTC) - timedelta(hours=1)
    return {
        "itemSummaries": [
            {
                "itemId": item_id,
                "title": title,
                "itemEndDate": end_time.isoformat().replace("+00:00", "Z"),
                "price": {"value": price, "currency": "USD"},
            }
        ]
    }


def _mock_http(browse_data: dict) -> MagicMock:
    token_resp = MagicMock()
    token_resp.raise_for_status.return_value = None
    token_resp.json.return_value = {"access_token": "fake"}

    browse_resp = MagicMock()
    browse_resp.status_code = 200
    browse_resp.text = ""
    browse_resp.raise_for_status.return_value = None
    browse_resp.json.return_value = browse_data

    client = MagicMock()
    client.post.return_value = token_resp
    client.get.return_value = browse_resp
    ctx = MagicMock()
    ctx.__enter__.return_value = client
    ctx.__exit__.return_value = False
    return ctx


_GRADED_TITLE = "PSA 10 Charizard Base Set Holo Rare"
_RAW_TITLE = "Charizard Base Set Holo Rare"

_patch_finding = patch(
    "backend.app.ingestion.ebay_sold._fetch_finding_completed",
    return_value=[],
)


def _patch_settings(**extra):
    defaults = {
        "ebay_app_id": "test-app-id",
        "ebay_cert_id": "test-cert-id",
        "ebay_search_keywords": "charizard",
        "ebay_sold_lookback_hours": 24,
    }
    defaults.update(extra)
    return patch.multiple("backend.app.ingestion.ebay_sold.settings", **defaults)


# ── Test 1 ────────────────────────────────────────────────────────────────────

def test_graded_title_creates_audit_row_when_enabled() -> None:
    """PSA 10 title + flag enabled → 1 audit row, 0 price_history rows."""
    with session_scope() as db:
        _create_asset(db)
        browse = _browse_response(title=_GRADED_TITLE, item_id="graded-001")

        with (
            _patch_settings(graded_shadow_audit_enabled=True),
            _patch_finding,
            patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=_mock_http(browse)),
        ):
            ingest_ebay_sold_cards(db)

        audit_rows = db.scalars(select(GradedObservationAudit)).all()
        price_rows = db.scalars(
            select(PriceHistory).where(PriceHistory.source == EBAY_SOLD_PRICE_SOURCE)
        ).all()

    assert len(audit_rows) == 1, f"expected 1 audit row, got {len(audit_rows)}"
    assert len(price_rows) == 0, f"graded listing must not write price_history"
    row = audit_rows[0]
    assert row.raw_title == _GRADED_TITLE
    assert row.shadow_decision is not None
    assert row.candidate_asset_id is not None


# ── Test 2 ────────────────────────────────────────────────────────────────────

def test_graded_title_skipped_when_disabled() -> None:
    """Same graded title + flag disabled → 0 audit rows, 0 price_history (unchanged pre-PR behavior)."""
    with session_scope() as db:
        _create_asset(db)
        browse = _browse_response(title=_GRADED_TITLE, item_id="graded-002")

        with (
            _patch_settings(graded_shadow_audit_enabled=False),
            _patch_finding,
            patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=_mock_http(browse)),
        ):
            ingest_ebay_sold_cards(db)

        audit_rows = db.scalars(select(GradedObservationAudit)).all()
        price_rows = db.scalars(
            select(PriceHistory).where(PriceHistory.source == EBAY_SOLD_PRICE_SOURCE)
        ).all()

    assert len(audit_rows) == 0, "flag disabled must produce zero audit rows"
    assert len(price_rows) == 0, "graded listing must never write price_history"


# ── Test 3 ────────────────────────────────────────────────────────────────────

def test_raw_listing_unaffected() -> None:
    """Raw (non-graded) listing → 0 audit rows, 1 price_history row. No regression."""
    with session_scope() as db:
        _create_asset(db)
        browse = _browse_response(title=_RAW_TITLE, item_id="raw-001")

        with (
            _patch_settings(graded_shadow_audit_enabled=True),
            _patch_finding,
            patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=_mock_http(browse)),
        ):
            ingest_ebay_sold_cards(db)

        audit_rows = db.scalars(select(GradedObservationAudit)).all()
        price_rows = db.scalars(
            select(PriceHistory).where(PriceHistory.source == EBAY_SOLD_PRICE_SOURCE)
        ).all()

    assert len(audit_rows) == 0, "raw listing must never write graded_observation_audit"
    assert len(price_rows) == 1, "raw listing must write price_history as before"


# ── Test 4 ────────────────────────────────────────────────────────────────────

def test_duplicate_audit_idempotent() -> None:
    """Same graded listing ingested twice → exactly 1 audit row (ON CONFLICT DO NOTHING)."""
    with session_scope() as db:
        _create_asset(db)
        browse = _browse_response(title=_GRADED_TITLE, item_id="graded-dedup")

        with (
            _patch_settings(graded_shadow_audit_enabled=True),
            _patch_finding,
            patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=_mock_http(browse)),
        ):
            ingest_ebay_sold_cards(db)
            ingest_ebay_sold_cards(db)  # second run with same item_id

        audit_rows = db.scalars(select(GradedObservationAudit)).all()

    assert len(audit_rows) == 1, (
        f"duplicate ingest must produce exactly 1 audit row, got {len(audit_rows)}"
    )


# ── Test 5 ────────────────────────────────────────────────────────────────────

from backend.app.ingestion.title_parser import TitleParseResult  # noqa: E402


@pytest.mark.parametrize("parse_result,expected_decision", [
    (
        TitleParseResult(market_segment="psa_10", grade_company="PSA", grade_score="10",
                         confidence="high", parser_notes=[], excluded=False),
        "audit_only",
    ),
    (
        TitleParseResult(market_segment="raw", grade_company=None, grade_score=None,
                         confidence="low", parser_notes=["grade not found"], excluded=False),
        "parser_raw",
    ),
    (
        TitleParseResult(market_segment="unknown", grade_company=None, grade_score=None,
                         confidence="low", parser_notes=["ambiguous grade"], excluded=False),
        "parser_unknown",
    ),
    (
        TitleParseResult(market_segment="unknown", grade_company=None, grade_score=None,
                         confidence="high", parser_notes=["excluded: lot"], excluded=True),
        "parser_excluded",
    ),
])
def test_parser_buckets_assigned_correctly(
    parse_result: TitleParseResult, expected_decision: str
) -> None:
    """shadow_decision is assigned based on parse_listing_title() output."""
    with session_scope() as db:
        _create_asset(db)
        browse = _browse_response(title=_GRADED_TITLE, item_id=f"bucket-{expected_decision}")

        with (
            _patch_settings(graded_shadow_audit_enabled=True),
            _patch_finding,
            patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=_mock_http(browse)),
            patch("backend.app.ingestion.ebay_sold.parse_listing_title", return_value=parse_result),
        ):
            ingest_ebay_sold_cards(db)

        rows = db.scalars(select(GradedObservationAudit)).all()

    assert len(rows) == 1, f"expected 1 audit row for {expected_decision}"
    assert rows[0].shadow_decision == expected_decision, (
        f"expected shadow_decision={expected_decision!r}, got {rows[0].shadow_decision!r}"
    )


# ── Test 6 ────────────────────────────────────────────────────────────────────

def test_compatibility_gate_failure_no_audit() -> None:
    """Graded title for wrong card name → name gate fails → zero audit rows."""
    with session_scope() as db:
        _create_asset(db, name="Charizard")
        # Title mentions a different card (Pikachu) — name gate should reject
        wrong_name_title = "PSA 10 Pikachu Base Set"
        browse = _browse_response(title=wrong_name_title, item_id="wrong-name-001")

        with (
            _patch_settings(graded_shadow_audit_enabled=True),
            _patch_finding,
            patch("backend.app.ingestion.ebay_sold.httpx.Client", return_value=_mock_http(browse)),
        ):
            ingest_ebay_sold_cards(db)

        audit_rows = db.scalars(select(GradedObservationAudit)).all()

    assert len(audit_rows) == 0, (
        "graded title that fails name gate must not create an audit row"
    )


# ── Tests 7-9: endpoint tests ─────────────────────────────────────────────────

def _make_backstage_app(db_session: Session) -> TestClient:
    app = FastAPI()
    app.include_router(backstage_router)

    def _override():
        yield db_session

    app.dependency_overrides[get_database] = _override
    return TestClient(app, raise_server_exceptions=True)


ADMIN_KEY = "test-admin-key"
_patch_admin_key = patch(
    "backend.app.backstage.routes.get_settings",
    return_value=MagicMock(admin_api_key=ADMIN_KEY, admin_emails=[], admin_email_set=set()),
)


def _admin(client: TestClient, method: str, path: str, **kwargs):
    return getattr(client, method)(
        path, headers={"X-Admin-Key": ADMIN_KEY}, **kwargs
    )


# ── Test 7 ────────────────────────────────────────────────────────────────────

def test_label_endpoint_updates_row() -> None:
    """POST /admin/diag/graded-shadow-admission/label with valid payload updates the row."""
    with session_scope() as db:
        row = GradedObservationAudit(
            provider="ebay_sold",
            external_item_id="item-label-test",
            candidate_asset_id=uuid.uuid4(),
            raw_title="PSA 10 Charizard Base",
            shadow_decision="audit_only",
            parser_market_segment="psa_10",
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        client = _make_backstage_app(db)
        with _patch_admin_key:
            resp = _admin(client, "post", "/admin/diag/graded-shadow-admission/label",
                          json={"id": str(row.id), "human_label": "graded_correct",
                                "reviewer_notes": "looks right"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["human_label"] == "graded_correct"
    assert body["human_reviewed_at"] is not None
    assert body["reviewer_notes"] == "looks right"


# ── Test 8 ────────────────────────────────────────────────────────────────────

def test_label_endpoint_rejects_invalid_label() -> None:
    """POST /label with unknown human_label value → 400."""
    with session_scope() as db:
        row = GradedObservationAudit(
            provider="ebay_sold",
            external_item_id="item-bad-label",
            candidate_asset_id=uuid.uuid4(),
            raw_title="PSA 10 Charizard Base",
            shadow_decision="audit_only",
            parser_market_segment="psa_10",
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        client = _make_backstage_app(db)
        with _patch_admin_key:
            resp = _admin(client, "post", "/admin/diag/graded-shadow-admission/label",
                          json={"id": str(row.id), "human_label": "definitely_valid_label"})

    assert resp.status_code == 400, resp.text


# ── Test 9 ────────────────────────────────────────────────────────────────────

def test_diag_endpoint_precision_summary() -> None:
    """Pre-populated audit rows with labels → diag endpoint precision numbers are correct."""
    with session_scope() as db:
        asset_id = uuid.uuid4()

        def _row(item_id: str, decision: str, segment: str, label: str | None) -> GradedObservationAudit:
            r = GradedObservationAudit(
                provider="ebay_sold",
                external_item_id=item_id,
                candidate_asset_id=asset_id,
                raw_title="PSA 10 Charizard Base",
                shadow_decision=decision,
                parser_market_segment=segment,
                human_label=label,
                human_reviewed_at=datetime.now(UTC) if label else None,
            )
            return r

        # 3 audit_only: 2 graded_correct, 1 wrong_segment
        db.add_all([
            _row("p1", "audit_only", "psa_10", "graded_correct"),
            _row("p2", "audit_only", "psa_10", "graded_correct"),
            _row("p3", "audit_only", "psa_10", "wrong_segment"),
            # 1 parser_raw: 1 graded_correct (false negative confirmed)
            _row("p4", "parser_raw", "raw", "graded_correct"),
            # 1 unreviewed
            _row("p5", "audit_only", "psa_10", None),
        ])
        db.commit()

        client = _make_backstage_app(db)
        with _patch_admin_key:
            resp = _admin(client, "get", "/admin/diag/graded-shadow-admission")

    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Total counts
    assert body["total_by_decision"]["audit_only"] == 4
    assert body["total_by_decision"]["parser_raw"] == 1
    assert body["reviewed_count"] == 4
    assert body["unreviewed_count"] == 1

    # Precision: audit_only has 2 correct, 1 wrong → 2/3
    ao = body["precision_by_decision"]["audit_only"]
    assert ao["graded_correct"] == 2
    assert ao["wrong_segment"] == 1

    assert body["removal_condition"] is not None
