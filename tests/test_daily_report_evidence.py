from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.app.models.daily_market_report import DailyMarketReport
from backend.app.schemas.catalyst import CatalystResponse
from backend.app.schemas.daily_report_intelligence import (
    DailyReportEvidenceBundle,
    DailyReportEvidenceCatalogItemResponse,
    DailyReportEvidenceRecord,
    DailyReportIntelligenceResponse,
    EvidenceSufficiency,
)
from backend.app.schemas.market import (
    MarketIndexResponse,
    MarketOverviewResponse,
    MarketSignalSummaryResponse,
    MarketTopMoverResponse,
)
from backend.app.services.daily_report_evidence import (
    EVIDENCE_SCHEMA_VERSION,
    build_daily_report_evidence_bundle,
    canonical_evidence_json,
    evaluate_evidence_sufficiency,
    evidence_hash,
    evidence_target_anchor,
    normalize_decimal,
    normalize_identifier,
)


AS_OF = datetime(2026, 7, 21, 10, 30, tzinfo=UTC)
REPORT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ASSET_A = UUID("11111111-1111-1111-1111-111111111111")
ASSET_B = UUID("22222222-2222-2222-2222-222222222222")
CATALYST_A = UUID("33333333-3333-3333-3333-333333333333")
CATALYST_B = UUID("44444444-4444-4444-4444-444444444444")


def _index(
    *,
    game: str = "pokemon",
    label: str = "Pokemon Market",
    observed_assets: int = 4,
) -> MarketIndexResponse:
    return MarketIndexResponse(
        game=game,
        label=label,
        change_pct=Decimal("0.0100"),
        direction="up",
        observed_assets=observed_assets,
        current_assets=6,
        confidence_label="medium",
    )


def _mover(
    *,
    asset_id: UUID = ASSET_A,
    name: str = "Charizard",
) -> MarketTopMoverResponse:
    return MarketTopMoverResponse(
        asset_id=asset_id,
        name=name,
        game="pokemon",
        set_name=None,
        latest_price=Decimal("120.00"),
        previous_price=Decimal("0.000"),
        percent_change=Decimal("1E+3"),
        absolute_change=Decimal("1E-7"),
        direction="up",
    )


def _signal(
    *,
    label: str = "BREAKOUT",
    count: int = 2,
) -> MarketSignalSummaryResponse:
    return MarketSignalSummaryResponse(
        label=label,
        count=count,
        average_confidence=Decimal("88.500"),
    )


def _overview(
    *,
    sentiment: str = "bullish",
    confidence: str = "medium",
    indexes: list[MarketIndexResponse] | None = None,
    movers: list[MarketTopMoverResponse] | None = None,
    signals: list[MarketSignalSummaryResponse] | None = None,
) -> dict:
    overview = MarketOverviewResponse(
        generated_at=AS_OF,
        market_sentiment=sentiment,
        confidence_label=confidence,
        indexes=[_index()] if indexes is None else indexes,
        top_movers=[_mover()] if movers is None else movers,
        signal_summary=[_signal()] if signals is None else signals,
        commentary="Persisted overview commentary.",
        evidence=["Persisted overview evidence is separate."],
    )
    return overview.model_dump(mode="json")


def _catalyst(
    *,
    catalyst_id: UUID = CATALYST_A,
    description: str = "Pokemon anniversary release",
    source_url: str = "https://example.com/catalyst",
    affected_games: list[str] | None = None,
    affected_asset_ids: list[str] | None = None,
    affected_set_ids: list[str] | None = None,
) -> dict:
    catalyst = CatalystResponse(
        id=catalyst_id,
        event_date=AS_OF + timedelta(days=2),
        active_until=AS_OF + timedelta(days=16),
        event_type="RELEASE",
        description=description,
        source_url=source_url,
        affected_games=affected_games or ["pokemon", "yugioh"],
        affected_asset_ids=affected_asset_ids or ["asset-b", "asset-a"],
        affected_set_ids=affected_set_ids or ["set-b", "set-a"],
        expected_window_days=14,
        impact_score=75,
        impact_label="high",
        confidence_score=Decimal("82.500"),
        confidence_label="high",
        status="upcoming",
        verified_at=AS_OF - timedelta(hours=2),
    )
    return catalyst.model_dump(mode="json")


def _report(**overrides) -> DailyMarketReport:
    values = {
        "id": REPORT_ID,
        "report_date": date(2026, 7, 21),
        "generated_at": AS_OF,
        "status": "published",
        "title": "Flashcard Planet Daily - 2026-07-21",
        "market_sentiment": "bullish",
        "confidence_label": "medium",
        "summary": "Persisted report summary.",
        "overview_json": _overview(),
        "evidence_json": ["Zulu evidence", "Alpha evidence"],
        "catalysts_json": [_catalyst()],
    }
    values.update(overrides)
    return DailyMarketReport(**values)


def test_build_bundle_has_exact_stable_id_order_across_all_kinds():
    bundle = build_daily_report_evidence_bundle(_report())

    assert bundle.schema_version == EVIDENCE_SCHEMA_VERSION == "daily-report-evidence-v1"
    assert [record.id for record in bundle.records] == [
        "index:pokemon",
        f"mover:{ASSET_A}",
        "signal:breakout",
        f"catalyst:{CATALYST_A}",
        "report:evidence:1",
        "report:evidence:2",
    ]
    assert [record.label for record in bundle.records] == [
        "Pokemon Market",
        "Charizard",
        "BREAKOUT",
        "Pokemon anniversary release",
        "Alpha evidence",
        "Zulu evidence",
    ]
    assert [record.source_record_id for record in bundle.records] == [
        "pokemon",
        str(ASSET_A),
        "BREAKOUT",
        str(CATALYST_A),
        "Alpha evidence",
        "Zulu evidence",
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("120.00"), "120"),
        ("0.0100", "0.01"),
        (Decimal("-0.000"), "0"),
        (Decimal("1E+3"), "1000"),
        (Decimal("1E-7"), "0.0000001"),
    ],
)
def test_normalize_decimal_uses_plain_canonical_form(value, expected):
    assert normalize_decimal(value) == expected
    assert "e" not in normalize_decimal(value).lower()


def test_normalize_identifier_collapses_non_alphanumeric_runs():
    assert normalize_identifier("  Pokemon__TCG / English  ") == "pokemon-tcg-english"


def test_normalize_identifier_transliterates_accented_latin_to_ascii():
    assert normalize_identifier("Pok\u00e9mon TCG") == "pokemon-tcg"
    assert normalize_identifier("Poke\u0301mon TCG") == "pokemon-tcg"


def test_normalize_identifier_hashes_non_latin_fallbacks_without_collisions():
    pokemon_japanese = normalize_identifier("\u30dd\u30b1\u30e2\u30f3")
    yugioh_japanese = normalize_identifier("\u904a\u622f\u738b")

    assert pokemon_japanese == "id-777e866794dd"
    assert yugioh_japanese == "id-70b84dcc51a0"
    assert pokemon_japanese != yugioh_japanese
    assert pokemon_japanese.isascii()
    assert yugioh_japanese.isascii()


def test_accented_game_name_builds_ascii_stable_id_and_anchor():
    report = _report(
        overview_json=_overview(
            indexes=[_index(game="Pok\u00e9mon", label="Pok\u00e9mon Market")]
        )
    )

    index_record = build_daily_report_evidence_bundle(report).records[0]

    assert index_record.id == "index:pokemon"
    assert index_record.source_record_id == "Pok\u00e9mon"
    assert index_record.target_anchor == evidence_target_anchor("index:pokemon")


def test_public_catalog_exposes_exact_privacy_safe_source_record_id():
    catalog_item = DailyReportEvidenceCatalogItemResponse(
        id=f"mover:{ASSET_A}",
        kind="mover",
        label="Charizard",
        source_record_id=str(ASSET_A),
        target_anchor="evidence-123456789abc",
    )

    assert catalog_item.source_record_id == str(ASSET_A)


def test_target_anchor_has_exact_prefix_length_and_hash():
    evidence_id = "signal:breakout"
    expected_digest = hashlib.sha256(evidence_id.encode("utf-8")).hexdigest()[:12]

    anchor = evidence_target_anchor(evidence_id)

    assert anchor == f"evidence-{expected_digest}"
    assert len(anchor) == 21


def test_bundle_converts_all_fact_values_and_canonicalizes_unordered_arrays():
    bundle = build_daily_report_evidence_bundle(_report())
    records = {record.kind: record for record in bundle.records if record.kind != "report_evidence"}

    assert records["index"].facts == {
        "game": "pokemon",
        "label": "Pokemon Market",
        "change_pct": "0.01",
        "direction": "up",
        "observed_assets": "4",
        "current_assets": "6",
        "confidence_label": "medium",
    }
    assert records["mover"].facts == {
        "asset_id": str(ASSET_A),
        "name": "Charizard",
        "game": "pokemon",
        "set_name": None,
        "latest_price": "120",
        "previous_price": "0",
        "percent_change": "1000",
        "absolute_change": "0.0000001",
        "direction": "up",
    }
    assert records["signal"].facts == {
        "label": "BREAKOUT",
        "count": "2",
        "average_confidence": "88.5",
    }
    assert records["catalyst"].facts == {
        "event_date": "2026-07-23T10:30:00+00:00",
        "active_until": "2026-08-06T10:30:00+00:00",
        "event_type": "RELEASE",
        "description": "Pokemon anniversary release",
        "affected_games": ["pokemon", "yugioh"],
        "affected_asset_ids": ["asset-a", "asset-b"],
        "affected_set_ids": ["set-a", "set-b"],
        "expected_window_days": "14",
        "impact_score": "75",
        "impact_label": "high",
        "confidence_score": "82.5",
        "confidence_label": "high",
        "status": "upcoming",
        "verified_at": "2026-07-21T08:30:00+00:00",
    }
    assert records["catalyst"].source_url == "https://example.com/catalyst"


def test_hash_ignores_generation_times_source_order_and_unordered_array_order():
    overview_a = _overview(
        indexes=[_index(game="yugioh", label="Yu-Gi-Oh Market"), _index()],
        movers=[_mover(asset_id=ASSET_B, name="Blue-Eyes"), _mover()],
        signals=[_signal(label="WATCH"), _signal()],
    )
    catalysts_a = [
        _catalyst(catalyst_id=CATALYST_B, description="Second catalyst"),
        _catalyst(),
    ]
    report_a = _report(
        overview_json=overview_a,
        evidence_json=["Zulu evidence", "Alpha evidence"],
        catalysts_json=catalysts_a,
    )

    overview_b = deepcopy(overview_a)
    overview_b["generated_at"] = "2026-07-22T00:00:00Z"
    for key in ("indexes", "top_movers", "signal_summary"):
        overview_b[key].reverse()
    catalysts_b = deepcopy(catalysts_a)
    catalysts_b.reverse()
    for catalyst in catalysts_b:
        catalyst["affected_games"].reverse()
        catalyst["affected_asset_ids"].reverse()
        catalyst["affected_set_ids"].reverse()
    report_b = _report(
        generated_at=AS_OF + timedelta(hours=8),
        overview_json=overview_b,
        evidence_json=["Alpha evidence", "Zulu evidence"],
        catalysts_json=catalysts_b,
    )

    assert evidence_hash(build_daily_report_evidence_bundle(report_a)) == evidence_hash(
        build_daily_report_evidence_bundle(report_b)
    )


@pytest.mark.parametrize("changed_value", ["fact", "source_url"])
def test_hash_changes_when_evidence_content_changes(changed_value):
    original = _report()
    overview = deepcopy(original.overview_json)
    catalysts = deepcopy(original.catalysts_json)
    if changed_value == "fact":
        overview["indexes"][0]["change_pct"] = "0.02"
    else:
        catalysts[0]["source_url"] = "https://example.com/changed"
    changed = _report(overview_json=overview, catalysts_json=catalysts)

    assert evidence_hash(build_daily_report_evidence_bundle(original)) != evidence_hash(
        build_daily_report_evidence_bundle(changed)
    )


def test_hash_ignores_whitespace_only_report_evidence_source_changes():
    normalized = _report(evidence_json=["Alpha evidence"])
    padded = _report(evidence_json=["  Alpha   evidence "])

    assert evidence_hash(
        build_daily_report_evidence_bundle(normalized)
    ) == evidence_hash(build_daily_report_evidence_bundle(padded))


def test_canonical_json_excludes_target_anchors():
    bundle = build_daily_report_evidence_bundle(_report())
    payload = json.loads(canonical_evidence_json(bundle))

    assert all("target_anchor" not in record for record in payload["records"])


def test_report_evidence_is_sorted_and_deduplicated_by_normalized_text():
    bundle = build_daily_report_evidence_bundle(
        _report(
            evidence_json=[
                "  Beta   evidence ",
                "Alpha evidence",
                "Alpha   evidence",
                "Beta evidence",
            ]
        )
    )
    evidence_records = [record for record in bundle.records if record.kind == "report_evidence"]

    assert [
        (record.id, record.label, record.source_record_id, record.facts)
        for record in evidence_records
    ] == [
        (
            "report:evidence:1",
            "Alpha evidence",
            "Alpha   evidence",
            {"text": "Alpha evidence"},
        ),
        (
            "report:evidence:2",
            "Beta evidence",
            "  Beta   evidence ",
            {"text": "Beta evidence"},
        ),
    ]


def test_none_catalyst_snapshot_matches_existing_empty_list_serialization():
    bundle = build_daily_report_evidence_bundle(_report(catalysts_json=None))

    assert all(record.kind != "catalyst" for record in bundle.records)


@pytest.mark.parametrize("snapshot", [{"bad": "overview"}, []])
def test_malformed_overview_snapshot_fails_pydantic_validation(snapshot):
    with pytest.raises(ValidationError):
        build_daily_report_evidence_bundle(_report(overview_json=snapshot))


@pytest.mark.parametrize("snapshot", [{"bad": "catalysts"}, [{"description": "incomplete"}]])
def test_malformed_catalyst_snapshot_fails_pydantic_validation(snapshot):
    with pytest.raises(ValidationError):
        build_daily_report_evidence_bundle(_report(catalysts_json=snapshot))


def test_duplicate_non_report_evidence_ids_fail_bundle_construction():
    duplicate_indexes = [
        _index(game="Pokemon TCG", label="First"),
        _index(game="pokemon---tcg", label="Second"),
    ]

    with pytest.raises(ValueError, match="duplicate evidence id: index:pokemon-tcg"):
        build_daily_report_evidence_bundle(
            _report(overview_json=_overview(indexes=duplicate_indexes))
        )


def test_sufficiency_checks_report_status_first():
    report = _report(
        status="draft",
        market_sentiment="insufficient_data",
        confidence_label="low",
        overview_json=_overview(indexes=[], movers=[], signals=[]),
    )
    bundle = build_daily_report_evidence_bundle(report)

    assert evaluate_evidence_sufficiency(report, bundle) == EvidenceSufficiency(
        sufficient=False,
        reason="report_not_published",
    )


def test_sufficiency_rejects_insufficient_sentiment():
    report = _report(market_sentiment="insufficient_data")
    bundle = build_daily_report_evidence_bundle(report)

    assert evaluate_evidence_sufficiency(report, bundle) == EvidenceSufficiency(
        sufficient=False,
        reason="insufficient_sentiment",
    )


@pytest.mark.parametrize("confidence", ["low", "insufficient_data"])
def test_sufficiency_rejects_low_or_insufficient_confidence(confidence):
    report = _report(confidence_label=confidence)
    bundle = build_daily_report_evidence_bundle(report)

    assert evaluate_evidence_sufficiency(report, bundle) == EvidenceSufficiency(
        sufficient=False,
        reason="low_confidence",
    )


def test_report_evidence_does_not_count_as_a_primary_record():
    report = _report(
        overview_json=_overview(movers=[], signals=[]),
        catalysts_json=[],
        evidence_json=["One", "Two", "Three"],
    )
    bundle = build_daily_report_evidence_bundle(report)

    assert evaluate_evidence_sufficiency(report, bundle) == EvidenceSufficiency(
        sufficient=False,
        reason="fewer_than_two_primary_records",
    )


def test_sufficiency_requires_an_index_with_three_observed_assets():
    report = _report(
        overview_json=_overview(indexes=[_index(observed_assets=2)]),
        catalysts_json=[],
    )
    bundle = build_daily_report_evidence_bundle(report)

    assert evaluate_evidence_sufficiency(report, bundle) == EvidenceSufficiency(
        sufficient=False,
        reason="insufficient_index_coverage",
    )


def test_two_primary_records_and_three_observed_assets_are_sufficient():
    report = _report(
        overview_json=_overview(
            indexes=[_index(observed_assets=3)],
            movers=[_mover()],
            signals=[],
        ),
        catalysts_json=[],
    )
    bundle = build_daily_report_evidence_bundle(report)

    assert evaluate_evidence_sufficiency(report, bundle) == EvidenceSufficiency(
        sufficient=True,
        reason="sufficient",
    )


def test_evidence_models_are_strict_forbid_extras_and_freeze_sufficiency():
    with pytest.raises(ValidationError):
        DailyReportEvidenceBundle(
            schema_version=EVIDENCE_SCHEMA_VERSION,
            report_id=str(REPORT_ID),
            report_date="2026-07-21",
            market_sentiment="bullish",
            confidence_label="medium",
            records=[],
        )
    with pytest.raises(ValidationError):
        DailyReportEvidenceRecord(
            id="index:pokemon",
            kind="index",
            label="Pokemon Market",
            facts={},
            source_url=None,
            source_record_id="pokemon",
            target_anchor="evidence-123456789abc",
            unexpected=True,
        )

    result = EvidenceSufficiency(sufficient=True, reason="sufficient")
    with pytest.raises(ValidationError):
        result.reason = "changed"


def test_public_response_defaults_do_not_share_mutable_lists():
    first = DailyReportIntelligenceResponse()
    second = DailyReportIntelligenceResponse()

    assert first.status == "unavailable"
    assert first.headline is None
    assert first.commentary is None
    assert first.risk_summary is None
    assert first.generated_at is None
    assert first.key_observations == []
    assert first.evidence_refs == []
    assert first.evidence_catalog == []

    first.key_observations.append(
        {"text": "Observation", "evidence_refs": ["index:pokemon"]}
    )
    first.evidence_refs.append("index:pokemon")
    first.evidence_catalog.append(
        {
            "id": "index:pokemon",
            "kind": "index",
            "label": "Pokemon Market",
            "source_record_id": "pokemon",
            "target_anchor": "evidence-123456789abc",
        }
    )

    assert second.key_observations == []
    assert second.evidence_refs == []
    assert second.evidence_catalog == []
