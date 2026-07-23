from __future__ import annotations

import json
from contextlib import AbstractContextManager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from sqlalchemy import JSON, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.models.daily_market_report import DailyMarketReport
from backend.app.models.daily_report_intelligence import DailyReportIntelligence
from backend.app.schemas.market import (
    MarketIndexResponse,
    MarketOverviewResponse,
    MarketTopMoverResponse,
)
from backend.app.services.daily_report_commentary import PROMPT_VERSION
from backend.app.services.daily_report_evidence import (
    build_daily_report_evidence_bundle,
    evidence_hash,
)
from backend.app.services.daily_report_intelligence_repository import (
    claim_generation_attempt,
)
from backend.app.services.daily_report_intelligence_service import (
    run_latest_daily_report_intelligence,
)
from backend.app.services.llm_provider import LLMTextResult


NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
REPORT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ASSET_ID = UUID("11111111-1111-1111-1111-111111111111")

VALID_RESPONSE = {
    "headline": "Pokemon market breadth improved",
    "headline_evidence_refs": ["index:pokemon"],
    "commentary": "Pokemon Market moved 12.34% in the captured snapshot.",
    "commentary_evidence_refs": ["index:pokemon"],
    "key_observations": [
        {
            "text": "Charizard moved 20%.",
            "evidence_refs": [f"mover:{ASSET_ID}"],
        }
    ],
    "risk_summary": "Coverage includes 4 observed assets.",
    "risk_evidence_refs": ["index:pokemon"],
}


def _overview() -> dict:
    overview = MarketOverviewResponse(
        generated_at=NOW,
        market_sentiment="bullish",
        confidence_label="high",
        indexes=[
            MarketIndexResponse(
                game="pokemon",
                label="Pokemon Market",
                change_pct=Decimal("12.34"),
                direction="up",
                observed_assets=4,
                current_assets=4,
                confidence_label="high",
            )
        ],
        top_movers=[
            MarketTopMoverResponse(
                asset_id=ASSET_ID,
                name="Charizard",
                game="pokemon",
                set_name="Base Set",
                latest_price=Decimal("120"),
                previous_price=Decimal("100"),
                percent_change=Decimal("20"),
                absolute_change=Decimal("20"),
                direction="up",
            )
        ],
        signal_summary=[],
        commentary="Persisted deterministic commentary.",
        evidence=[],
    )
    return overview.model_dump(mode="json")


def _report(*, confidence_label: str = "high") -> DailyMarketReport:
    return DailyMarketReport(
        id=REPORT_ID,
        report_date=date(2026, 7, 21),
        generated_at=NOW,
        status="published",
        title="Flashcard Planet Daily",
        market_sentiment="bullish",
        confidence_label=confidence_label,
        summary="Persisted report summary.",
        overview_json=_overview(),
        evidence_json=["Captured persisted evidence."],
        catalysts_json=[],
        created_at=NOW,
        updated_at=NOW,
    )


class TrackingSessionContext(AbstractContextManager[Session]):
    def __init__(self, factory: "TrackingSessionFactory") -> None:
        self.factory = factory
        self.session: Session | None = None

    def __enter__(self) -> Session:
        self.session = Session(self.factory.engine)
        self.factory.open_count += 1
        return self.session

    def __exit__(self, exc_type, exc, traceback) -> None:
        assert self.session is not None
        self.session.close()
        self.factory.open_count -= 1


class TrackingSessionFactory:
    def __init__(self, engine) -> None:
        self.engine = engine
        self.open_count = 0

    def __call__(self) -> TrackingSessionContext:
        return TrackingSessionContext(self)


@pytest.fixture
def session_factory(canonical_model_column_types) -> TrackingSessionFactory:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = TrackingSessionFactory(engine)
    with Session(engine) as db:
        db.add(_report())
        db.commit()
    try:
        yield factory
    finally:
        engine.dispose()
        for column, original_type in canonical_model_column_types:
            column.type = original_type


@pytest.fixture
def valid_provider() -> MagicMock:
    provider = MagicMock()
    provider.result = LLMTextResult(
        text=json.dumps(VALID_RESPONSE),
        provider="groq",
        model="test-model",
    )
    provider.generate_text_result.return_value = provider.result
    return provider


def _intelligence_rows(
    session_factory: TrackingSessionFactory,
) -> list[DailyReportIntelligence]:
    with Session(session_factory.engine) as db:
        return list(db.scalars(select(DailyReportIntelligence)).all())


def test_provider_call_happens_with_no_open_session(
    session_factory: TrackingSessionFactory,
    valid_provider: MagicMock,
) -> None:
    def assert_closed(*_args, **_kwargs):
        assert session_factory.open_count == 0
        return valid_provider.result

    valid_provider.generate_text_result.side_effect = assert_closed

    outcome = run_latest_daily_report_intelligence(
        session_factory=session_factory,
        provider_factory=lambda: valid_provider,
        now=NOW,
    )

    assert outcome.status == "published"
    assert outcome.records_written == 1
    assert session_factory.open_count == 0


def test_insufficient_report_never_resolves_provider(
    session_factory: TrackingSessionFactory,
) -> None:
    with Session(session_factory.engine) as db:
        report = db.get(DailyMarketReport, REPORT_ID)
        assert report is not None
        report.confidence_label = "low"
        db.commit()
    provider_factory = MagicMock()

    outcome = run_latest_daily_report_intelligence(
        session_factory=session_factory,
        provider_factory=provider_factory,
        now=NOW,
    )

    assert outcome.status == "insufficient_evidence"
    assert outcome.records_written == 1
    provider_factory.assert_not_called()
    row = _intelligence_rows(session_factory)[0]
    assert row.commentary == "Insufficient evidence."


def test_same_hash_published_run_is_noop(
    session_factory: TrackingSessionFactory,
    valid_provider: MagicMock,
) -> None:
    first = run_latest_daily_report_intelligence(
        session_factory=session_factory,
        provider_factory=lambda: valid_provider,
        now=NOW,
    )
    second = run_latest_daily_report_intelligence(
        session_factory=session_factory,
        provider_factory=lambda: valid_provider,
        now=NOW,
    )

    assert first.status == "published"
    assert second.status == "noop"
    assert second.reason == "published"
    assert valid_provider.generate_text_result.call_count == 1


def test_changed_report_during_call_records_stale_evidence(
    session_factory: TrackingSessionFactory,
    valid_provider: MagicMock,
) -> None:
    def mutate_report(*_args, **_kwargs):
        assert session_factory.open_count == 0
        with Session(session_factory.engine) as db:
            report = db.get(DailyMarketReport, REPORT_ID)
            assert report is not None
            report.evidence_json = [*report.evidence_json, "Changed evidence."]
            db.commit()
        return valid_provider.result

    valid_provider.generate_text_result.side_effect = mutate_report

    outcome = run_latest_daily_report_intelligence(
        session_factory=session_factory,
        provider_factory=lambda: valid_provider,
        now=NOW,
    )

    assert outcome.status == "failed"
    assert outcome.error_code == "stale_evidence"
    assert outcome.records_written == 1
    row = _intelligence_rows(session_factory)[0]
    assert row.status == "failed"
    assert row.error_code == "stale_evidence"
    assert row.commentary is None


def test_no_report_is_a_noop_without_provider_resolution(
    session_factory: TrackingSessionFactory,
) -> None:
    with Session(session_factory.engine) as db:
        db.query(DailyMarketReport).delete()
        db.commit()
    provider_factory = MagicMock()

    outcome = run_latest_daily_report_intelligence(
        session_factory=session_factory,
        provider_factory=provider_factory,
        now=NOW,
    )

    assert outcome.status == "noop"
    assert outcome.reason == "no_report"
    assert outcome.records_written == 0
    provider_factory.assert_not_called()


def test_provider_unavailable_is_recorded_as_failure(
    session_factory: TrackingSessionFactory,
) -> None:
    provider = MagicMock()
    provider.generate_text_result.return_value = None

    outcome = run_latest_daily_report_intelligence(
        session_factory=session_factory,
        provider_factory=lambda: provider,
        now=NOW,
    )

    assert outcome.status == "failed"
    assert outcome.error_code == "provider_unavailable"
    assert outcome.records_written == 1
    assert _intelligence_rows(session_factory)[0].provider is None


def test_validation_failure_is_recorded_without_raw_output(
    session_factory: TrackingSessionFactory,
) -> None:
    provider = MagicMock()
    provider.generate_text_result.return_value = LLMTextResult(
        text="raw secret response",
        provider="openai",
        model="test-model",
    )

    outcome = run_latest_daily_report_intelligence(
        session_factory=session_factory,
        provider_factory=lambda: provider,
        now=NOW,
    )

    assert outcome.status == "failed"
    assert outcome.error_code == "invalid_json"
    row = _intelligence_rows(session_factory)[0]
    assert row.error_code == "invalid_json"
    assert "raw secret response" not in repr(row.__dict__)


def test_provider_factory_exception_is_recorded_as_internal_error(
    session_factory: TrackingSessionFactory,
) -> None:
    provider_factory = MagicMock(side_effect=RuntimeError("secret provider error"))

    outcome = run_latest_daily_report_intelligence(
        session_factory=session_factory,
        provider_factory=provider_factory,
        now=NOW,
    )

    assert outcome.status == "failed"
    assert outcome.error_code == "internal_error"
    assert outcome.records_written == 1
    row = _intelligence_rows(session_factory)[0]
    assert row.error_code == "internal_error"
    assert "secret provider error" not in repr(row.__dict__)


def test_superseded_stale_claim_returns_noop_without_overwriting_new_attempt(
    session_factory: TrackingSessionFactory,
    valid_provider: MagicMock,
) -> None:
    def reclaim_and_mutate(*_args, **_kwargs):
        with Session(session_factory.engine) as db:
            report = db.get(DailyMarketReport, REPORT_ID)
            assert report is not None
            original_digest = evidence_hash(
                build_daily_report_evidence_bundle(report)
            )
            reclaimed = claim_generation_attempt(
                db,
                report.id,
                original_digest,
                PROMPT_VERSION,
                now=NOW + timedelta(minutes=15),
            )
            assert reclaimed.claim is not None
            assert reclaimed.claim.attempt_count == 2
            report.evidence_json = [*report.evidence_json, "Changed evidence."]
            db.commit()
        return valid_provider.result

    valid_provider.generate_text_result.side_effect = reclaim_and_mutate

    outcome = run_latest_daily_report_intelligence(
        session_factory=session_factory,
        provider_factory=lambda: valid_provider,
        now=NOW,
    )

    assert outcome.status == "noop"
    assert outcome.reason == "superseded_attempt"
    assert outcome.records_written == 0
    row = _intelligence_rows(session_factory)[0]
    assert row.status == "pending"
    assert row.attempt_count == 2


def test_exhausted_attempts_do_not_resolve_provider_again(
    session_factory: TrackingSessionFactory,
) -> None:
    provider = MagicMock()
    provider.generate_text_result.return_value = None

    outcomes = [
        run_latest_daily_report_intelligence(
            session_factory=session_factory,
            provider_factory=lambda: provider,
            now=NOW,
        )
        for _ in range(4)
    ]

    assert [outcome.status for outcome in outcomes] == [
        "failed",
        "failed",
        "failed",
        "noop",
    ]
    assert outcomes[-1].reason == "attempts_exhausted"
    assert provider.generate_text_result.call_count == 3


def test_recent_pending_does_not_resolve_provider(
    session_factory: TrackingSessionFactory,
) -> None:
    with Session(session_factory.engine) as db:
        report = db.get(DailyMarketReport, REPORT_ID)
        assert report is not None
        digest = evidence_hash(build_daily_report_evidence_bundle(report))
        decision = claim_generation_attempt(
            db,
            report.id,
            digest,
            PROMPT_VERSION,
            now=NOW,
        )
        assert decision.claim is not None
    provider_factory = MagicMock()

    outcome = run_latest_daily_report_intelligence(
        session_factory=session_factory,
        provider_factory=provider_factory,
        now=NOW,
    )

    assert outcome.status == "noop"
    assert outcome.reason == "recent_pending"
    provider_factory.assert_not_called()


def test_unexpected_preparation_exception_is_not_swallowed(
    session_factory: TrackingSessionFactory,
) -> None:
    provider_factory = MagicMock()

    with patch(
        "backend.app.services.daily_report_intelligence_service."
        "build_daily_report_evidence_bundle",
        side_effect=RuntimeError("database preparation failed"),
    ):
        with pytest.raises(RuntimeError, match="database preparation failed"):
            run_latest_daily_report_intelligence(
                session_factory=session_factory,
                provider_factory=provider_factory,
                now=NOW,
            )

    assert session_factory.open_count == 0
    provider_factory.assert_not_called()
