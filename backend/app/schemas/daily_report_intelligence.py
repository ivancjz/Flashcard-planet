from __future__ import annotations

from datetime import date, datetime
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field


EvidenceKind = Literal["index", "mover", "signal", "catalyst", "report_evidence"]
PublicIntelligenceStatus = Literal[
    "published",
    "insufficient_evidence",
    "unavailable",
]
FactValue: TypeAlias = str | list[str] | None


class DailyReportEvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    kind: EvidenceKind
    label: str
    facts: dict[str, FactValue]
    source_url: str | None
    target_anchor: str


class DailyReportEvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["daily-report-evidence-v1"] = "daily-report-evidence-v1"
    report_id: str
    report_date: date
    market_sentiment: str
    confidence_label: str
    records: list[DailyReportEvidenceRecord]


class EvidenceSufficiency(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    sufficient: bool
    reason: str


class DailyReportIntelligenceObservationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    text: str
    evidence_refs: list[str]


class DailyReportEvidenceCatalogItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str
    kind: EvidenceKind
    label: str
    target_anchor: str


class DailyReportIntelligenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: PublicIntelligenceStatus = "unavailable"
    headline: str | None = None
    commentary: str | None = None
    risk_summary: str | None = None
    key_observations: list[DailyReportIntelligenceObservationResponse] = Field(
        default_factory=list
    )
    evidence_refs: list[str] = Field(default_factory=list)
    evidence_catalog: list[DailyReportEvidenceCatalogItemResponse] = Field(
        default_factory=list
    )
    generated_at: datetime | None = None
