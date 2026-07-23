from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import JSON, create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.models.daily_market_report import DailyMarketReport
from backend.app.models.daily_report_intelligence import DailyReportIntelligence
from backend.app.services.daily_report_commentary import (
    PROMPT_VERSION,
    CommentaryGenerationResult,
    CommentaryObservation,
    ValidatedDailyReportCommentary,
)
from backend.app.services.daily_report_intelligence_repository import (
    ClaimDecision,
    claim_generation_attempt,
    get_latest_published_report,
    load_intelligence_candidates,
    persist_insufficient_evidence,
    record_generation_failure,
    record_generation_success,
)


NOW = datetime(2026, 7, 21, 2, 0, tzinfo=UTC)
DIGEST = "a" * 64


@pytest.fixture
def repository_db(canonical_model_column_types) -> Session:
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, JSONB):
                column.type = JSON()

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        for column, original_type in canonical_model_column_types:
            column.type = original_type


def _report(
    *,
    report_date: date = date(2026, 7, 21),
    status: str = "published",
) -> DailyMarketReport:
    return DailyMarketReport(
        id=uuid4(),
        report_date=report_date,
        generated_at=NOW,
        status=status,
        title="Flashcard Planet Daily",
        market_sentiment="bullish",
        confidence_label="high",
        summary="Observed market summary.",
        overview_json={},
        evidence_json=[],
        catalysts_json=[],
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.fixture
def report_row(repository_db: Session) -> DailyMarketReport:
    report = _report()
    repository_db.add(report)
    repository_db.commit()
    return report


def _valid_result() -> CommentaryGenerationResult:
    commentary = ValidatedDailyReportCommentary(
        headline="Pokemon market breadth improved",
        headline_evidence_refs=["index:pokemon"],
        commentary="Pokemon Market moved 12.34% in the captured snapshot.",
        commentary_evidence_refs=["index:pokemon"],
        key_observations=[
            CommentaryObservation(
                text="Charizard moved 20%.",
                evidence_refs=[
                    "mover:11111111-1111-1111-1111-111111111111"
                ],
            )
        ],
        risk_summary="Coverage includes 4 observed assets.",
        risk_evidence_refs=["index:pokemon"],
    )
    return CommentaryGenerationResult(
        commentary=commentary,
        provider="groq",
        model="test-model",
        error_code=None,
    )


def _row_for_claim(
    db: Session,
    intelligence_id: UUID,
) -> DailyReportIntelligence:
    row = db.get(DailyReportIntelligence, intelligence_id)
    assert row is not None
    return row


def test_get_latest_published_report_ignores_newer_unpublished_rows(
    repository_db: Session,
) -> None:
    older = _report(report_date=date(2026, 7, 20))
    latest = _report(report_date=date(2026, 7, 21))
    draft = _report(report_date=date(2026, 7, 22), status="failed")
    repository_db.add_all([older, latest, draft])
    repository_db.commit()

    result = get_latest_published_report(repository_db)

    assert result is not None
    assert result.id == latest.id


def test_new_cache_key_is_claimed_once(
    repository_db: Session,
    report_row: DailyMarketReport,
) -> None:
    first = claim_generation_attempt(
        repository_db,
        report_row.id,
        DIGEST,
        PROMPT_VERSION,
        now=NOW,
    )
    second = claim_generation_attempt(
        repository_db,
        report_row.id,
        DIGEST,
        PROMPT_VERSION,
        now=NOW,
    )

    assert first.claim is not None
    assert first.claim.attempt_count == 1
    assert second == ClaimDecision(claim=None, reason="recent_pending")


def test_failed_attempt_retries_until_three(
    repository_db: Session,
    report_row: DailyMarketReport,
) -> None:
    for expected in (1, 2, 3):
        decision = claim_generation_attempt(
            repository_db,
            report_row.id,
            DIGEST,
            PROMPT_VERSION,
            now=NOW,
        )
        assert decision.claim is not None
        assert decision.claim.attempt_count == expected
        assert record_generation_failure(
            repository_db,
            decision.claim,
            "invalid_json",
            now=NOW,
        )

    exhausted = claim_generation_attempt(
        repository_db,
        report_row.id,
        DIGEST,
        PROMPT_VERSION,
        now=NOW,
    )
    assert exhausted == ClaimDecision(claim=None, reason="attempts_exhausted")


def test_stale_pending_is_reclaimed_after_fifteen_minutes(
    repository_db: Session,
    report_row: DailyMarketReport,
) -> None:
    first = claim_generation_attempt(
        repository_db,
        report_row.id,
        DIGEST,
        PROMPT_VERSION,
        now=NOW,
    )
    second = claim_generation_attempt(
        repository_db,
        report_row.id,
        DIGEST,
        PROMPT_VERSION,
        now=NOW + timedelta(minutes=15),
    )

    assert first.claim is not None
    assert second.claim is not None
    assert second.claim.attempt_count == 2


def test_published_and_insufficient_rows_are_terminal(
    repository_db: Session,
    report_row: DailyMarketReport,
) -> None:
    published = claim_generation_attempt(
        repository_db,
        report_row.id,
        DIGEST,
        PROMPT_VERSION,
        now=NOW,
    )
    assert published.claim is not None
    assert record_generation_success(
        repository_db,
        published.claim,
        _valid_result(),
        now=NOW,
    )
    assert (
        claim_generation_attempt(
            repository_db,
            report_row.id,
            DIGEST,
            PROMPT_VERSION,
            now=NOW,
        ).reason
        == "published"
    )

    other_digest = "b" * 64
    assert persist_insufficient_evidence(
        repository_db,
        report_row.id,
        other_digest,
        PROMPT_VERSION,
        now=NOW,
    )
    assert (
        claim_generation_attempt(
            repository_db,
            report_row.id,
            other_digest,
            PROMPT_VERSION,
            now=NOW,
        ).reason
        == "insufficient_evidence"
    )
    assert not persist_insufficient_evidence(
        repository_db,
        report_row.id,
        other_digest,
        PROMPT_VERSION,
        now=NOW,
    )


def test_insufficient_transition_resets_prior_attempt_count(
    repository_db: Session,
    report_row: DailyMarketReport,
) -> None:
    decision = claim_generation_attempt(
        repository_db,
        report_row.id,
        DIGEST,
        PROMPT_VERSION,
        now=NOW,
    )
    assert decision.claim is not None
    assert record_generation_failure(
        repository_db,
        decision.claim,
        "provider_unavailable",
        now=NOW,
    )

    assert persist_insufficient_evidence(
        repository_db,
        report_row.id,
        DIGEST,
        PROMPT_VERSION,
        now=NOW + timedelta(minutes=1),
    )

    row = repository_db.get(
        DailyReportIntelligence,
        decision.claim.intelligence_id,
    )
    assert row is not None
    assert row.status == "insufficient_evidence"
    assert row.attempt_count == 0


def test_changed_hash_gets_independent_cache_row(
    repository_db: Session,
    report_row: DailyMarketReport,
) -> None:
    first = claim_generation_attempt(
        repository_db,
        report_row.id,
        "a" * 64,
        PROMPT_VERSION,
        now=NOW,
    )
    second = claim_generation_attempt(
        repository_db,
        report_row.id,
        "b" * 64,
        PROMPT_VERSION,
        now=NOW,
    )

    assert first.claim is not None
    assert second.claim is not None
    assert first.claim.intelligence_id != second.claim.intelligence_id


def test_successful_publication_maps_all_fields(
    repository_db: Session,
    report_row: DailyMarketReport,
) -> None:
    decision = claim_generation_attempt(
        repository_db,
        report_row.id,
        DIGEST,
        PROMPT_VERSION,
        now=NOW,
    )
    assert decision.claim is not None

    written = record_generation_success(
        repository_db,
        decision.claim,
        _valid_result(),
        now=NOW,
    )
    row = _row_for_claim(repository_db, decision.claim.intelligence_id)

    assert written
    assert row.status == "published"
    assert row.headline == "Pokemon market breadth improved"
    assert row.commentary == (
        "Pokemon Market moved 12.34% in the captured snapshot."
    )
    assert row.risk_summary == "Coverage includes 4 observed assets."
    assert row.key_observations_json == ["Charizard moved 20%."]
    assert row.evidence_refs_json == {
        "headline": ["index:pokemon"],
        "commentary": ["index:pokemon"],
        "key_observations": [
            ["mover:11111111-1111-1111-1111-111111111111"]
        ],
        "risk_summary": ["index:pokemon"],
    }
    assert row.provider == "groq"
    assert row.model == "test-model"
    assert row.generated_at == NOW.replace(tzinfo=None)
    assert row.error_code is None


def test_failure_clears_publish_only_fields(
    repository_db: Session,
    report_row: DailyMarketReport,
) -> None:
    decision = claim_generation_attempt(
        repository_db,
        report_row.id,
        DIGEST,
        PROMPT_VERSION,
        now=NOW,
    )
    assert decision.claim is not None
    row = _row_for_claim(repository_db, decision.claim.intelligence_id)
    row.headline = "stale headline"
    row.commentary = "stale commentary"
    row.risk_summary = "stale risk"
    row.key_observations_json = ["stale observation"]
    row.evidence_refs_json = {"headline": ["stale"]}
    row.provider = "openai"
    row.model = "stale-model"
    row.generated_at = NOW
    repository_db.commit()

    assert record_generation_failure(
        repository_db,
        decision.claim,
        "invalid_json",
        now=NOW,
    )

    row = _row_for_claim(repository_db, decision.claim.intelligence_id)
    assert row.status == "failed"
    assert row.error_code == "invalid_json"
    assert row.headline is None
    assert row.commentary is None
    assert row.risk_summary is None
    assert row.key_observations_json == []
    assert row.evidence_refs_json == {}
    assert row.provider is None
    assert row.model is None
    assert row.generated_at is None


def test_stale_claim_cannot_overwrite_a_reclaimed_attempt(
    repository_db: Session,
    report_row: DailyMarketReport,
) -> None:
    first = claim_generation_attempt(
        repository_db,
        report_row.id,
        DIGEST,
        PROMPT_VERSION,
        now=NOW,
    )
    second = claim_generation_attempt(
        repository_db,
        report_row.id,
        DIGEST,
        PROMPT_VERSION,
        now=NOW + timedelta(minutes=15),
    )
    assert first.claim is not None
    assert second.claim is not None

    assert not record_generation_success(
        repository_db,
        first.claim,
        _valid_result(),
        now=NOW + timedelta(minutes=16),
    )
    row = _row_for_claim(repository_db, second.claim.intelligence_id)
    assert row.status == "pending"
    assert row.attempt_count == 2


def test_competing_insert_is_reloaded_without_recursive_claim(
    report_row: DailyMarketReport,
) -> None:
    intelligence_id = uuid4()
    competing_row = DailyReportIntelligence(
        id=intelligence_id,
        report_id=report_row.id,
        evidence_hash=DIGEST,
        prompt_version=PROMPT_VERSION,
        status="pending",
        attempt_count=1,
        key_observations_json=[],
        evidence_refs_json={},
        created_at=NOW,
        updated_at=NOW,
    )
    missing_result = MagicMock()
    missing_result.scalar_one_or_none.return_value = None
    competing_result = MagicMock()
    competing_result.scalar_one_or_none.return_value = competing_row
    db = MagicMock()
    db.execute.side_effect = [missing_result, competing_result]
    db.commit.side_effect = IntegrityError("insert", {}, Exception("race"))

    decision = claim_generation_attempt(
        db,
        report_row.id,
        DIGEST,
        PROMPT_VERSION,
        now=NOW,
    )

    assert decision == ClaimDecision(claim=None, reason="recent_pending")
    assert db.execute.call_count == 2
    db.rollback.assert_called_once()


def test_load_candidates_batches_multiple_report_ids_in_one_query(
    repository_db: Session,
) -> None:
    first_report = _report(report_date=date(2026, 7, 20))
    second_report = _report(report_date=date(2026, 7, 21))
    repository_db.add_all([first_report, second_report])
    repository_db.commit()
    first_claim = claim_generation_attempt(
        repository_db,
        first_report.id,
        "a" * 64,
        PROMPT_VERSION,
        now=NOW,
    )
    second_claim = claim_generation_attempt(
        repository_db,
        second_report.id,
        "b" * 64,
        PROMPT_VERSION,
        now=NOW,
    )
    assert first_claim.claim is not None
    assert second_claim.claim is not None
    first_report_id = first_report.id
    second_report_id = second_report.id
    missing_report_id = uuid4()

    statements: list[str] = []

    def track_statement(
        _conn,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        statements.append(statement)

    event.listen(
        repository_db.get_bind(),
        "before_cursor_execute",
        track_statement,
    )
    try:
        candidates = load_intelligence_candidates(
            repository_db,
            [first_report_id, second_report_id, missing_report_id],
        )
    finally:
        event.remove(
            repository_db.get_bind(),
            "before_cursor_execute",
            track_statement,
        )

    selects = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("SELECT")
    ]
    assert len(selects) == 1
    assert [row.id for row in candidates[first_report_id]] == [
        first_claim.claim.intelligence_id
    ]
    assert [row.id for row in candidates[second_report_id]] == [
        second_claim.claim.intelligence_id
    ]
    assert candidates[missing_report_id] == []


def test_load_candidates_empty_input_issues_no_query(
    repository_db: Session,
) -> None:
    assert load_intelligence_candidates(repository_db, []) == {}
    assert repository_db.scalars(
        select(DailyReportIntelligence)
    ).all() == []
