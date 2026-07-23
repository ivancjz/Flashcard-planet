from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import TypeAdapter

from backend.app.models.daily_market_report import DailyMarketReport
from backend.app.schemas.catalyst import CatalystResponse
from backend.app.schemas.daily_report_intelligence import (
    DailyReportEvidenceBundle,
    DailyReportEvidenceRecord,
    EvidenceSufficiency,
    FactValue,
)
from backend.app.schemas.market import MarketOverviewResponse


EVIDENCE_SCHEMA_VERSION = "daily-report-evidence-v1"

_CATALYST_SNAPSHOT_ADAPTER = TypeAdapter(list[CatalystResponse])
_KIND_RANK = {
    "index": 0,
    "mover": 1,
    "signal": 2,
    "catalyst": 3,
    "report_evidence": 4,
}
_PRIMARY_KINDS = frozenset({"index", "mover", "signal", "catalyst"})
_NON_ASCII_IDENTIFIER_RUN = re.compile(r"[^a-z0-9]+")


def normalize_identifier(value: str) -> str:
    stripped = value.strip()
    decomposed = unicodedata.normalize("NFKD", stripped)
    ascii_value = decomposed.encode("ascii", "ignore").decode("ascii").lower()
    identifier = _NON_ASCII_IDENTIFIER_RUN.sub("-", ascii_value).strip("-")
    if identifier:
        return identifier

    fallback_source = unicodedata.normalize("NFKC", stripped).casefold()
    digest = hashlib.sha256(fallback_source.encode("utf-8")).hexdigest()[:12]
    return f"id-{digest}"


def normalize_decimal(value: Decimal | str | int | float) -> str:
    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    if not decimal_value.is_finite():
        raise ValueError("decimal value must be finite")
    if decimal_value == 0:
        return "0"

    plain = format(decimal_value, "f")
    if "." in plain:
        plain = plain.rstrip("0").rstrip(".")
    return plain


def evidence_target_anchor(evidence_id: str) -> str:
    digest = hashlib.sha256(evidence_id.encode("utf-8")).hexdigest()[:12]
    return f"evidence-{digest}"


def _utc_isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _scalar_fact(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return normalize_decimal(value)
    if isinstance(value, datetime):
        return _utc_isoformat(value)
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, UUID):
        return str(value).lower()
    return str(value)


def _string_array(values: list[Any], *, unordered: bool = False) -> list[str]:
    converted = [str(value.value) if isinstance(value, Enum) else str(value) for value in values]
    return sorted(converted) if unordered else converted


def _record(
    *,
    evidence_id: str,
    kind: str,
    label: str,
    source_record_id: str | None,
    facts: dict[str, FactValue],
    source_url: str | None = None,
) -> DailyReportEvidenceRecord:
    return DailyReportEvidenceRecord(
        id=evidence_id,
        kind=kind,
        label=label,
        source_record_id=source_record_id,
        facts=facts,
        source_url=source_url,
        target_anchor=evidence_target_anchor(evidence_id),
    )


def _normalized_report_evidence(
    values: list[Any] | None,
) -> list[tuple[str, str]]:
    raw_values_by_label: dict[str, set[str]] = {}
    for value in values or []:
        raw_value = str(value)
        label = " ".join(raw_value.split())
        if label:
            raw_values_by_label.setdefault(label, set()).add(raw_value)
    return [
        (label, min(raw_values))
        for label, raw_values in sorted(raw_values_by_label.items())
    ]


def build_daily_report_evidence_bundle(
    report: DailyMarketReport,
) -> DailyReportEvidenceBundle:
    overview = MarketOverviewResponse.model_validate(report.overview_json)
    catalyst_snapshot = [] if report.catalysts_json is None else report.catalysts_json
    catalysts = _CATALYST_SNAPSHOT_ADAPTER.validate_python(catalyst_snapshot)
    records: list[DailyReportEvidenceRecord] = []
    seen_ids: set[str] = set()

    def add(record: DailyReportEvidenceRecord) -> None:
        if record.id in seen_ids:
            raise ValueError(f"duplicate evidence id: {record.id}")
        seen_ids.add(record.id)
        records.append(record)

    for index in overview.indexes:
        evidence_id = f"index:{normalize_identifier(index.game)}"
        add(
            _record(
                evidence_id=evidence_id,
                kind="index",
                label=index.label,
                source_record_id=index.game,
                facts={
                    "game": _scalar_fact(index.game),
                    "label": _scalar_fact(index.label),
                    "change_pct": normalize_decimal(index.change_pct),
                    "direction": _scalar_fact(index.direction),
                    "observed_assets": _scalar_fact(index.observed_assets),
                    "current_assets": _scalar_fact(index.current_assets),
                    "confidence_label": _scalar_fact(index.confidence_label),
                },
            )
        )

    for mover in overview.top_movers:
        canonical_asset_id = str(mover.asset_id).lower()
        evidence_id = f"mover:{canonical_asset_id}"
        add(
            _record(
                evidence_id=evidence_id,
                kind="mover",
                label=mover.name,
                source_record_id=canonical_asset_id,
                facts={
                    "asset_id": canonical_asset_id,
                    "name": _scalar_fact(mover.name),
                    "game": _scalar_fact(mover.game),
                    "set_name": _scalar_fact(mover.set_name),
                    "latest_price": normalize_decimal(mover.latest_price),
                    "previous_price": normalize_decimal(mover.previous_price),
                    "percent_change": normalize_decimal(mover.percent_change),
                    "absolute_change": normalize_decimal(mover.absolute_change),
                    "direction": _scalar_fact(mover.direction),
                },
            )
        )

    for signal in overview.signal_summary:
        evidence_id = f"signal:{normalize_identifier(signal.label)}"
        add(
            _record(
                evidence_id=evidence_id,
                kind="signal",
                label=signal.label,
                source_record_id=signal.label,
                facts={
                    "label": _scalar_fact(signal.label),
                    "count": _scalar_fact(signal.count),
                    "average_confidence": _scalar_fact(signal.average_confidence),
                },
            )
        )

    for catalyst in catalysts:
        canonical_catalyst_id = str(catalyst.id).lower()
        evidence_id = f"catalyst:{canonical_catalyst_id}"
        add(
            _record(
                evidence_id=evidence_id,
                kind="catalyst",
                label=catalyst.description,
                source_record_id=canonical_catalyst_id,
                source_url=catalyst.source_url,
                facts={
                    "event_date": _scalar_fact(catalyst.event_date),
                    "active_until": _scalar_fact(catalyst.active_until),
                    "event_type": _scalar_fact(catalyst.event_type),
                    "description": _scalar_fact(catalyst.description),
                    "affected_games": _string_array(
                        catalyst.affected_games,
                        unordered=True,
                    ),
                    "affected_asset_ids": _string_array(
                        catalyst.affected_asset_ids,
                        unordered=True,
                    ),
                    "affected_set_ids": _string_array(
                        catalyst.affected_set_ids,
                        unordered=True,
                    ),
                    "expected_window_days": _scalar_fact(
                        catalyst.expected_window_days
                    ),
                    "impact_score": _scalar_fact(catalyst.impact_score),
                    "impact_label": _scalar_fact(catalyst.impact_label),
                    "confidence_score": _scalar_fact(catalyst.confidence_score),
                    "confidence_label": _scalar_fact(catalyst.confidence_label),
                    "status": _scalar_fact(catalyst.status),
                    "verified_at": _scalar_fact(catalyst.verified_at),
                },
            )
        )

    for position, (text, source_record_id) in enumerate(
        _normalized_report_evidence(report.evidence_json),
        start=1,
    ):
        evidence_id = f"report:evidence:{position}"
        add(
            _record(
                evidence_id=evidence_id,
                kind="report_evidence",
                label=text,
                source_record_id=source_record_id,
                facts={"text": text},
            )
        )

    records.sort(key=lambda record: (_KIND_RANK[record.kind], record.id))
    return DailyReportEvidenceBundle(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        report_id=str(report.id),
        report_date=report.report_date,
        market_sentiment=report.market_sentiment,
        confidence_label=report.confidence_label,
        records=records,
    )


def canonical_evidence_json(bundle: DailyReportEvidenceBundle) -> str:
    payload = bundle.model_dump(mode="json")
    for record in payload["records"]:
        record.pop("target_anchor", None)
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def evidence_hash(bundle: DailyReportEvidenceBundle) -> str:
    canonical = canonical_evidence_json(bundle)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _index_has_required_coverage(record: DailyReportEvidenceRecord) -> bool:
    observed_assets = record.facts.get("observed_assets")
    if not isinstance(observed_assets, str):
        return False
    try:
        return str(int(observed_assets)) == observed_assets and int(observed_assets) >= 3
    except ValueError:
        return False


def evaluate_evidence_sufficiency(
    report: DailyMarketReport,
    bundle: DailyReportEvidenceBundle,
) -> EvidenceSufficiency:
    if report.status != "published":
        return EvidenceSufficiency(
            sufficient=False,
            reason="report_not_published",
        )
    if bundle.market_sentiment == "insufficient_data":
        return EvidenceSufficiency(
            sufficient=False,
            reason="insufficient_sentiment",
        )
    if bundle.confidence_label not in {"medium", "high"}:
        return EvidenceSufficiency(
            sufficient=False,
            reason="low_confidence",
        )

    primary_records = [
        record for record in bundle.records if record.kind in _PRIMARY_KINDS
    ]
    if len(primary_records) < 2:
        return EvidenceSufficiency(
            sufficient=False,
            reason="fewer_than_two_primary_records",
        )
    if not any(
        record.kind == "index" and _index_has_required_coverage(record)
        for record in bundle.records
    ):
        return EvidenceSufficiency(
            sufficient=False,
            reason="insufficient_index_coverage",
        )
    return EvidenceSufficiency(sufficient=True, reason="sufficient")
