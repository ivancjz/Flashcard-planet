# Daily Report AI Commentary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add asynchronous, evidence-grounded AI commentary to the latest persisted Daily Market Report without making report generation or public reads depend on an LLM.

**Architecture:** The deterministic report remains authoritative and publishes first. An hourly worker builds a canonical evidence bundle, claims one cached attempt, closes the database session, calls the routed provider, validates strict JSON and citations, then publishes through a fresh session. Existing Daily Report GET responses receive an additive privacy-safe `intelligence` object, and the Dashboard and report detail page render it with deterministic fallbacks.

**Tech Stack:** Python 3.13, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, PostgreSQL JSONB, APScheduler, pytest, React 19, TypeScript 6, Vitest, Testing Library, Vite.

---

## Execution Preconditions

- PR #83 must be merged before Task 1. It removes the public report-generation POST route and repairs fresh-session scheduler failure logging.
- Start the implementation worktree from the updated `origin/main`, not from the documentation branch.
- Read `docs/superpowers/specs/2026-07-22-daily-report-ai-commentary-design.md` before each task. The spec is authoritative when a snippet below needs a mechanical adjustment to fit the merged code.
- Never make a live LLM request from tests.
- Keep `DAILY_REPORT_AI_ENABLED=false` until staging verification is complete.

## File Map

### Backend files to create

- `backend/app/models/daily_report_intelligence.py`: ORM persistence and database invariants.
- `backend/app/schemas/daily_report_intelligence.py`: internal evidence models and public API models.
- `backend/app/services/daily_report_evidence.py`: canonical bundle creation, sufficiency, anchors, and hashing.
- `backend/app/services/daily_report_commentary.py`: prompt, strict parser, evidence validation, and provider call.
- `backend/app/services/daily_report_intelligence_repository.py`: claims, retries, final status transitions, and batch reads.
- `backend/app/services/daily_report_intelligence_service.py`: cross-session orchestration with no session held over the network call.
- `migrations/versions/0043_add_daily_report_intelligence.py`: reversible table migration.
- `tests/test_daily_report_intelligence_migration.py`: migration contract tests.
- `tests/test_daily_report_evidence.py`: canonical evidence and sufficiency tests.
- `tests/test_daily_report_commentary.py`: strict output and safety validation tests.
- `tests/test_daily_report_intelligence_repository.py`: persistence state-machine tests.
- `tests/test_daily_report_intelligence_service.py`: orchestration and transaction-boundary tests.

### Backend files to modify

- `backend/app/models/__init__.py`: register the new ORM model.
- `backend/app/services/llm_provider.py`: additive metadata result and Daily Report route.
- `backend/app/core/config.py`: feature flag and interval.
- `.env.example`: operator configuration.
- `backend/app/services/scheduler_run_log_service.py`: job identifier.
- `backend/app/backstage/scheduler.py`: hourly worker registration and fresh-session run logging.
- `backend/app/schemas/daily_market_report.py`: additive `intelligence` field.
- `backend/app/services/daily_market_report_service.py`: current-hash selection and bulk intelligence loading.
- `tests/test_llm_provider.py`: metadata and routing coverage.
- `tests/test_daily_market_report_scheduler.py`: registration and run outcomes.
- `tests/test_scheduler_startup.py`: feature-flag registration coverage.
- `tests/test_daily_market_report_service.py`: published/insufficient/unavailable serialization and batch loading.
- `tests/test_daily_market_report_api.py`: public contract and GET-only regression.

### Frontend files to create

- `frontend/src/components/DailyReportEvidenceLinks.tsx`: shared citation resolution and links.
- `frontend/src/components/DailyReportEvidenceLinks.test.tsx`: catalog and missing-reference behavior.

### Frontend files to modify

- `frontend/src/types/api.ts`: intelligence, observation, and evidence-catalog types.
- `frontend/src/pages/DashboardPage.tsx`: published AI summary and deterministic fallback.
- `frontend/src/pages/DashboardPage.test.tsx`: Dashboard intelligence states and links.
- `frontend/src/pages/DailyReportDetailPage.tsx`: AI section and evidence anchors.
- `frontend/src/pages/DailyReportDetailPage.test.tsx`: AI states, plain-text safety, and anchor targets.
- `frontend/src/pages/DailyReportsPage.test.tsx`: required unavailable-intelligence fixture value.
- `frontend/src/styles/theme.css`: commentary, citation, focus-target, and mobile styles.
- `docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md`: Phase 5 completion evidence after verification.

---

### Task 0: Sync The Security Dependency And Establish A Baseline

**Files:**
- Verify: `backend/app/api/routes/market.py`
- Verify: `backend/app/backstage/scheduler.py`
- Verify: `tests/test_daily_market_report_api.py`
- Verify: `tests/test_daily_market_report_scheduler.py`

- [ ] **Step 1: Confirm PR #83 is merged**

Run:

```powershell
gh pr view 83 --repo ivancjz/Flashcard-planet --json state,isDraft,mergedAt
```

Expected: `state` is `MERGED`, `isDraft` is `false`, and `mergedAt` is non-null. Stop the implementation if this is not true.

- [ ] **Step 2: Create the implementation worktree from updated main**

Run from the primary repository:

```powershell
git fetch origin --prune
git worktree add -b feat/daily-report-ai-commentary "C:\Users\ivan cheng\.config\superpowers\worktrees\Flashcard-planet\daily-report-ai-implementation" origin/main
```

Expected: the new worktree tracks the latest `origin/main` and has no local changes.

- [ ] **Step 3: Verify the two PR #83 invariants**

Run:

```powershell
rg -n "daily-report/generate|create_daily_market_report" backend/app/api/routes/market.py tests/test_daily_market_report_api.py
rg -n -C 20 "def _run_daily_market_report_snapshot" backend/app/backstage/scheduler.py
```

Expected: no public generate route or API test remains; report scheduler failure logging closes or rolls back the report session and finishes the run through a fresh session.

- [ ] **Step 4: Run the focused baseline**

Run:

```powershell
python -m pytest tests/test_daily_market_report_service.py tests/test_daily_market_report_api.py tests/test_daily_market_report_scheduler.py tests/test_llm_provider.py -q
```

Expected: all selected tests pass before Phase 5 changes.

- [ ] **Step 5: Record the baseline without creating a commit**

Run:

```powershell
git status --short --branch
git log -1 --oneline
```

Expected: clean `feat/daily-report-ai-commentary` worktree based on the merged PR #83 main commit.

---

### Task 1: Add The Intelligence Persistence Model And Migration

**Files:**
- Create: `backend/app/models/daily_report_intelligence.py`
- Create: `migrations/versions/0043_add_daily_report_intelligence.py`
- Create: `tests/test_daily_report_intelligence_migration.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write failing model and migration tests**

Create `tests/test_daily_report_intelligence_migration.py` with tests that import migration `0043`, inspect the ORM table, and assert the complete contract:

```python
from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, call

import sqlalchemy as sa

from backend.app.models.daily_report_intelligence import DailyReportIntelligence


def _load_migration():
    path = Path(__file__).parent.parent / "migrations" / "versions" / "0043_add_daily_report_intelligence.py"
    spec = importlib.util.spec_from_file_location("migration_0043", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    migration.op = MagicMock()
    return migration


def test_model_has_cache_key_and_private_generation_fields():
    table = DailyReportIntelligence.__table__
    assert set(table.columns.keys()) == {
        "id", "report_id", "evidence_hash", "prompt_version", "status",
        "headline", "commentary", "risk_summary", "key_observations_json",
        "evidence_refs_json", "provider", "model", "attempt_count",
        "error_code", "generated_at", "created_at", "updated_at",
    }
    unique_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }
    assert ("report_id", "evidence_hash", "prompt_version") in unique_sets


def test_upgrade_creates_table_constraints_and_indexes():
    migration = _load_migration()
    migration.upgrade()
    create_tables = [item for item in migration.op.method_calls if item[0] == "create_table"]
    assert len(create_tables) == 1
    assert create_tables[0].args[0] == "daily_report_intelligence"
    assert call.create_index("ix_daily_report_intelligence_report_id", "daily_report_intelligence", ["report_id"]) in migration.op.method_calls
    assert call.create_index("ix_daily_report_intelligence_status_updated", "daily_report_intelligence", ["status", "updated_at"]) in migration.op.method_calls


def test_downgrade_removes_only_intelligence_table():
    migration = _load_migration()
    migration.downgrade()
    assert migration.op.method_calls == [
        call.drop_index("ix_daily_report_intelligence_status_updated", table_name="daily_report_intelligence"),
        call.drop_index("ix_daily_report_intelligence_report_id", table_name="daily_report_intelligence"),
        call.drop_table("daily_report_intelligence"),
    ]
```

- [ ] **Step 2: Run the new tests and confirm failure**

Run:

```powershell
python -m pytest tests/test_daily_report_intelligence_migration.py -q
```

Expected: collection fails because the model and migration do not exist.

- [ ] **Step 3: Create the ORM model**

Create `backend/app/models/daily_report_intelligence.py` with this public shape and named constraints:

```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from backend.app.db.base import Base


class DailyReportIntelligence(Base):
    __tablename__ = "daily_report_intelligence"
    __table_args__ = (
        UniqueConstraint("report_id", "evidence_hash", "prompt_version", name="uq_daily_report_intelligence_cache_key"),
        CheckConstraint("status IN ('pending','published','insufficient_evidence','failed')", name="ck_daily_report_intelligence_status"),
        CheckConstraint("attempt_count BETWEEN 0 AND 3", name="ck_daily_report_intelligence_attempt_count"),
        Index("ix_daily_report_intelligence_status_updated", "status", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("daily_market_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    commentary: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_observations_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    evidence_refs_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
```

Import and export `DailyReportIntelligence` in `backend/app/models/__init__.py`.

- [ ] **Step 4: Create migration 0043**

Create the table with the same names and defaults as the ORM model. Use `server_default=sa.text("'[]'::jsonb")`, `server_default=sa.text("'{}'::jsonb")`, and `server_default="0"`; create the two explicit indexes in the same order expected by the test. Set `down_revision = "0042"`. The downgrade drops the composite index, report index, then the table.

Core migration constraints must be:

```python
sa.ForeignKeyConstraint(["report_id"], ["daily_market_reports.id"], ondelete="CASCADE"),
sa.UniqueConstraint("report_id", "evidence_hash", "prompt_version", name="uq_daily_report_intelligence_cache_key"),
sa.CheckConstraint("status IN ('pending','published','insufficient_evidence','failed')", name="ck_daily_report_intelligence_status"),
sa.CheckConstraint("attempt_count BETWEEN 0 AND 3", name="ck_daily_report_intelligence_attempt_count"),
```

- [ ] **Step 5: Run persistence tests**

Run:

```powershell
python -m pytest tests/test_daily_report_intelligence_migration.py -q
python -m compileall backend/app/models/daily_report_intelligence.py migrations/versions/0043_add_daily_report_intelligence.py
```

Expected: migration tests pass and both files compile.

- [ ] **Step 6: Commit persistence**

```powershell
git add backend/app/models/daily_report_intelligence.py backend/app/models/__init__.py migrations/versions/0043_add_daily_report_intelligence.py tests/test_daily_report_intelligence_migration.py
git commit -m "feat: add daily report intelligence persistence"
```

---

### Task 2: Build Canonical Evidence Bundles And Sufficiency Rules

**Files:**
- Create: `backend/app/schemas/daily_report_intelligence.py`
- Create: `backend/app/services/daily_report_evidence.py`
- Create: `tests/test_daily_report_evidence.py`

- [ ] **Step 1: Write failing evidence tests**

Create a report-row factory using `DailyMarketReport` and frozen snapshot JSON. Cover these exact behaviors:

```python
def test_bundle_assigns_stable_ids_and_canonical_order(report_row):
    bundle = build_daily_report_evidence_bundle(report_row)
    assert [record.id for record in bundle.records] == [
        "index:pokemon",
        "mover:11111111-1111-1111-1111-111111111111",
        "signal:breakout",
        "catalyst:22222222-2222-2222-2222-222222222222",
        "report:evidence:1",
        "report:evidence:2",
    ]
    assert [record.source_record_id for record in bundle.records] == [
        "pokemon",
        "11111111-1111-1111-1111-111111111111",
        "BREAKOUT",
        "22222222-2222-2222-2222-222222222222",
        None,
        None,
    ]
    assert bundle.records[0].facts["change_pct"] == "12.34"
    assert bundle.records[0].target_anchor.startswith("evidence-")


def test_hash_ignores_generation_time_and_source_order(report_row):
    first = evidence_hash(build_daily_report_evidence_bundle(report_row))
    report_row.generated_at = report_row.generated_at + timedelta(hours=1)
    report_row.evidence_json = list(reversed(report_row.evidence_json))
    second = evidence_hash(build_daily_report_evidence_bundle(report_row))
    assert second == first


def test_hash_changes_when_a_fact_changes(report_row):
    first = evidence_hash(build_daily_report_evidence_bundle(report_row))
    report_row.overview_json["indexes"][0]["change_pct"] = "12.35"
    assert evidence_hash(build_daily_report_evidence_bundle(report_row)) != first


@pytest.mark.parametrize("confidence", ["low", "insufficient"])
def test_low_or_insufficient_confidence_skips_llm(report_row, confidence):
    report_row.confidence_label = confidence
    decision = evaluate_evidence_sufficiency(report_row, build_daily_report_evidence_bundle(report_row))
    assert decision.sufficient is False


def test_sufficiency_requires_two_primary_records_and_index_coverage(report_row):
    report_row.overview_json["top_movers"] = []
    report_row.overview_json["signal_summary"] = []
    report_row.catalysts_json = []
    decision = evaluate_evidence_sufficiency(report_row, build_daily_report_evidence_bundle(report_row))
    assert decision == EvidenceSufficiency(sufficient=False, reason="fewer_than_two_primary_records")
```

Also test duplicate normalized report evidence is retained once, numeric decimals never use exponent notation, and every `target_anchor` is 21 characters (`evidence-` plus 12 hex characters). Add Unicode cases proving accented Latin transliterates to ASCII, non-Latin-only identifiers receive distinct deterministic hash fallbacks, and `source_record_id` retains the exact public source key for frontend lookup.

- [ ] **Step 2: Run tests and confirm missing-module failure**

```powershell
python -m pytest tests/test_daily_report_evidence.py -q
```

Expected: collection fails because evidence schemas and service do not exist.

- [ ] **Step 3: Define evidence and public schemas**

In `backend/app/schemas/daily_report_intelligence.py`, define strict Pydantic models:

```python
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EvidenceKind = Literal["index", "mover", "signal", "catalyst", "report_evidence"]
PublicIntelligenceStatus = Literal["published", "insufficient_evidence", "unavailable"]
FactValue = str | list[str] | None


class DailyReportEvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: EvidenceKind
    label: str
    source_record_id: str | None
    facts: dict[str, FactValue]
    source_url: str | None = None
    target_anchor: str


class DailyReportEvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["daily-report-evidence-v1"] = "daily-report-evidence-v1"
    report_id: str
    report_date: date
    market_sentiment: str
    confidence_label: str
    records: list[DailyReportEvidenceRecord]


class EvidenceSufficiency(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sufficient: bool
    reason: str


class DailyReportIntelligenceObservationResponse(BaseModel):
    text: str
    evidence_refs: list[str]


class DailyReportEvidenceCatalogItemResponse(BaseModel):
    id: str
    kind: EvidenceKind
    label: str
    source_record_id: str | None
    target_anchor: str


class DailyReportIntelligenceResponse(BaseModel):
    status: PublicIntelligenceStatus = "unavailable"
    headline: str | None = None
    commentary: str | None = None
    risk_summary: str | None = None
    key_observations: list[DailyReportIntelligenceObservationResponse] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    evidence_catalog: list[DailyReportEvidenceCatalogItemResponse] = Field(default_factory=list)
    generated_at: datetime | None = None
```

- [ ] **Step 4: Implement deterministic evidence conversion**

In `backend/app/services/daily_report_evidence.py`, define `EVIDENCE_SCHEMA_VERSION = "daily-report-evidence-v1"` and expose `normalize_identifier`, `normalize_decimal`, `evidence_target_anchor`, `build_daily_report_evidence_bundle`, `canonical_evidence_json`, `evidence_hash`, and `evaluate_evidence_sufficiency` with the argument and return types established by the tests in Step 1.

Implement normalization with these concrete operations:

```python
import hashlib
import json
import re
import unicodedata
from decimal import Decimal

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

def normalize_decimal(value: object) -> str:
    number = Decimal(str(value))
    if number == 0:
        return "0"
    rendered = format(number.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered

def evidence_target_anchor(evidence_id: str) -> str:
    digest = hashlib.sha256(evidence_id.encode("utf-8")).hexdigest()[:12]
    return f"evidence-{digest}"

def canonical_evidence_json(bundle: DailyReportEvidenceBundle) -> str:
    payload = bundle.model_dump(mode="json")
    for record in payload["records"]:
        record.pop("target_anchor", None)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def evidence_hash(bundle: DailyReportEvidenceBundle) -> str:
    return hashlib.sha256(canonical_evidence_json(bundle).encode("utf-8")).hexdigest()
```

Build records in five separate private functions, one per evidence kind. Sort each kind by ID; sort and deduplicate report evidence by normalized text before assigning one-based IDs. Convert `overview_json` through `MarketOverviewResponse.model_validate` and catalysts through `TypeAdapter(list[CatalystResponse])` so malformed snapshots fail before prompting.

Every record must set the privacy-safe `source_record_id` explicitly: exact index `game`, canonical mover asset UUID, exact signal label, canonical catalyst UUID, and `None` for free-form report evidence. This field is part of the canonical bundle and hash. It must contain only identifiers already present in the public persisted report; never place provider, model, cache, prompt, or internal database metadata in it.

Implement the sufficiency checks in spec order and return these stable reasons: `report_not_published`, `insufficient_sentiment`, `low_confidence`, `fewer_than_two_primary_records`, `insufficient_index_coverage`, or `sufficient`.

- [ ] **Step 5: Run evidence tests**

```powershell
python -m pytest tests/test_daily_report_evidence.py -q
```

Expected: all evidence, hash, anchor, and sufficiency tests pass.

- [ ] **Step 6: Commit evidence contracts**

```powershell
git add backend/app/schemas/daily_report_intelligence.py backend/app/services/daily_report_evidence.py tests/test_daily_report_evidence.py
git commit -m "feat: build daily report evidence bundles"
```

---

### Task 3: Add Metadata-Capable LLM Results And Task Routing

**Files:**
- Modify: `backend/app/services/llm_provider.py`
- Modify: `tests/test_llm_provider.py`

- [ ] **Step 1: Add failing provider metadata tests**

Append tests with concrete provider fakes:

```python
def test_daily_report_commentary_routes_to_openai_then_groq():
    import backend.app.services.llm_provider as m
    provider = m.get_llm_provider_for_task("daily_report_commentary")
    assert isinstance(provider, m.FallbackLLMProvider)
    assert isinstance(provider._primary, m.OpenAIProvider)
    assert isinstance(provider._fallback, m.GroqProvider)


def test_fallback_result_reports_actual_successful_provider():
    import backend.app.services.llm_provider as m
    primary = MagicMock()
    primary.generate_text_result.return_value = None
    fallback = MagicMock()
    fallback.generate_text_result.return_value = m.LLMTextResult(
        text='{"headline":"ok"}', provider="groq", model="fallback-model"
    )
    result = m.FallbackLLMProvider(primary, fallback).generate_text_result("sys", "user", 900)
    assert result == m.LLMTextResult(text='{"headline":"ok"}', provider="groq", model="fallback-model")


def test_existing_text_only_fallback_still_calls_generate_text():
    import backend.app.services.llm_provider as m
    primary = MagicMock()
    primary.generate_text.return_value = "existing result"
    fallback = MagicMock()
    result = m.FallbackLLMProvider(primary, fallback).generate_text("sys", "user", 256)
    assert result == "existing result"
    primary.generate_text_result.assert_not_called()
```

- [ ] **Step 2: Run the new provider tests and confirm failure**

```powershell
python -m pytest tests/test_llm_provider.py -q
```

Expected: failures mention missing `LLMTextResult`, missing `generate_text_result`, and missing route.

- [ ] **Step 3: Add the metadata result without changing text-only behavior**

Add:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMTextResult:
    text: str
    provider: str
    model: str


class MetadataLLMProvider(LLMProvider, Protocol):
    def generate_text_result(self, system: str, user: str, max_tokens: int) -> LLMTextResult | None:
        pass
```

Change `FallbackLLMProvider.__init__` annotations from `LLMProvider` to `MetadataLLMProvider` for both primary and fallback. This matches the new method used by `generate_text_result` while leaving runtime behavior unchanged.

Keep each existing `generate_text` implementation unchanged. Add one method to each concrete provider that delegates to it and records the configured provider/model:

```python
def generate_text_result(self, system: str, user: str, max_tokens: int) -> LLMTextResult | None:
    text = self.generate_text(system, user, max_tokens)
    if text is None:
        return None
    return LLMTextResult(text=text, provider="openai", model=_setting_value("OPENAI_MODEL", "openai_model", "gpt-4o-mini"))
```

Use `provider="anthropic"` with `ANTHROPIC_MODEL` for Anthropic and `provider="groq"` with `GROQ_MODEL` for Groq.

Add this independent method to `FallbackLLMProvider`; do not alter its existing `generate_text` method:

```python
def generate_text_result(self, system: str, user: str, max_tokens: int) -> LLMTextResult | None:
    primary = self._primary.generate_text_result(system, user, max_tokens)
    if primary is not None:
        return primary
    _log("llm_primary_returned_none_using_fallback", level=logging.INFO,
         primary=type(self._primary).__name__, fallback=type(self._fallback).__name__)
    return self._fallback.generate_text_result(system, user, max_tokens)
```

Add `"daily_report_commentary": ("openai", "groq")` to `_TASK_ROUTING` and include the task name in the routing docstring.

- [ ] **Step 4: Run provider regression tests**

```powershell
python -m pytest tests/test_llm_provider.py tests/test_noise_filter.py -q
```

Expected: new metadata tests and all existing text-only consumers pass.

- [ ] **Step 5: Commit provider support**

```powershell
git add backend/app/services/llm_provider.py tests/test_llm_provider.py
git commit -m "feat: track LLM provider generation metadata"
```

---

### Task 4: Implement The Strict Commentary Prompt And Validator

**Files:**
- Create: `backend/app/services/daily_report_commentary.py`
- Create: `tests/test_daily_report_commentary.py`

- [ ] **Step 1: Write failing prompt and validation tests**

Create a valid model response helper and test the complete rejection surface:

```python
VALID_RESPONSE = {
    "headline": "Pokemon market breadth improved",
    "headline_evidence_refs": ["index:pokemon"],
    "commentary": "Pokemon Market moved 12.34% in the captured snapshot.",
    "commentary_evidence_refs": ["index:pokemon"],
    "key_observations": [
        {"text": "Charizard moved 20%.", "evidence_refs": ["mover:11111111-1111-1111-1111-111111111111"]}
    ],
    "risk_summary": "Coverage includes 4 observed assets.",
    "risk_evidence_refs": ["index:pokemon"],
}


def test_prompt_delimits_untrusted_canonical_evidence(bundle):
    system, user = build_commentary_prompt(bundle)
    assert "untrusted data" in system.lower()
    assert "<evidence_data>" in user
    assert "</evidence_data>" in user
    assert user.count("<evidence_data>") == 1


def test_valid_output_is_parsed_with_per_field_citations(bundle):
    parsed = parse_and_validate_commentary(json.dumps(VALID_RESPONSE), bundle)
    assert parsed.headline == "Pokemon market breadth improved"
    assert parsed.key_observations[0].evidence_refs == ["mover:11111111-1111-1111-1111-111111111111"]


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("```json\n{}\n```", "invalid_json"),
        (json.dumps({**VALID_RESPONSE, "extra": True}), "invalid_schema"),
        (json.dumps({**VALID_RESPONSE, "headline_evidence_refs": ["index:unknown"]}), "unknown_evidence_reference"),
        (json.dumps({**VALID_RESPONSE, "commentary": "Pokemon moved 99.99%."}), "unsupported_number"),
        (json.dumps({**VALID_RESPONSE, "commentary": "[Read this](https://example.com)"}), "forbidden_markup"),
        (json.dumps({**VALID_RESPONSE, "commentary": "Buy Pokemon cards."}), "forbidden_recommendation"),
        (json.dumps({**VALID_RESPONSE, "commentary": "The move was caused by the event."}), "unsupported_causality"),
    ],
)
def test_invalid_output_returns_stable_code(bundle, raw, code):
    with pytest.raises(CommentaryValidationError) as exc:
        parse_and_validate_commentary(raw, bundle)
    assert exc.value.code == code


def test_provider_none_returns_provider_unavailable(bundle):
    provider = MagicMock()
    provider.generate_text_result.return_value = None
    result = generate_daily_report_commentary(bundle, provider)
    assert result.error_code == "provider_unavailable"
    assert result.commentary is None
```

Also parameterize duplicate references, empty references, more than three observations, over-length fields, URL schemes, backticks, HTML, `will rise`, `price target`, `because`, and numeric tokens supported only by an unreferenced record.

- [ ] **Step 2: Run tests and confirm failure**

```powershell
python -m pytest tests/test_daily_report_commentary.py -q
```

Expected: collection fails because the commentary module does not exist.

- [ ] **Step 3: Define strict internal output models and typed results**

In `backend/app/services/daily_report_commentary.py`, define:

```python
PROMPT_VERSION = "daily-report-commentary-v1"
MAX_COMMENTARY_TOKENS = 900


class CommentaryValidationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CommentaryObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=400)
    evidence_refs: list[str] = Field(min_length=1, max_length=5)


class ValidatedDailyReportCommentary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    headline: str = Field(min_length=1, max_length=180)
    headline_evidence_refs: list[str] = Field(min_length=1, max_length=5)
    commentary: str = Field(min_length=1, max_length=1200)
    commentary_evidence_refs: list[str] = Field(min_length=1, max_length=8)
    key_observations: list[CommentaryObservation] = Field(min_length=1, max_length=3)
    risk_summary: str = Field(min_length=1, max_length=600)
    risk_evidence_refs: list[str] = Field(min_length=1, max_length=5)


@dataclass(frozen=True)
class CommentaryGenerationResult:
    commentary: ValidatedDailyReportCommentary | None
    provider: str | None
    model: str | None
    error_code: str | None
```

- [ ] **Step 4: Implement prompt construction and strict validation**

Expose `build_commentary_prompt(bundle) -> tuple[str, str]`, `parse_and_validate_commentary(raw, bundle) -> ValidatedDailyReportCommentary`, and `generate_daily_report_commentary(bundle, provider) -> CommentaryGenerationResult`.

Use `json.loads(raw)` directly and `ValidatedDailyReportCommentary.model_validate(payload)`. Convert JSON and Pydantic exceptions to `CommentaryValidationError("invalid_json")` and `CommentaryValidationError("invalid_schema")`.

Validation order after schema parsing must be references, duplicate references, numeric tokens, markup, recommendations, then causality. Use whole-word case-insensitive regexes for the deny lists in the design. Numeric validation gathers tokens with `(?<![A-Za-z])[-+]?\d+(?:\.\d+)?%?` and checks each token, without `%`, against the normalized values in report context and only the records referenced by that field.

The generation wrapper catches `CommentaryValidationError` and returns its code, catches unexpected exceptions as `internal_error`, and never includes raw text in an exception or log.

- [ ] **Step 5: Run commentary tests**

```powershell
python -m pytest tests/test_daily_report_commentary.py tests/test_llm_provider.py -q
```

Expected: all strict-output and provider tests pass with no network access.

- [ ] **Step 6: Commit prompt and validator**

```powershell
git add backend/app/services/daily_report_commentary.py tests/test_daily_report_commentary.py
git commit -m "feat: validate evidence-grounded report commentary"
```

---

### Task 5: Implement The Claim And Retry Repository

**Files:**
- Create: `backend/app/services/daily_report_intelligence_repository.py`
- Create: `tests/test_daily_report_intelligence_repository.py`

- [ ] **Step 1: Write failing repository state tests**

Use the existing in-memory SQLAlchemy fixture pattern, coercing JSONB to JSON. Cover:

```python
def test_new_cache_key_is_claimed_once(sqlite_db, report_row, bundle):
    first = claim_generation_attempt(sqlite_db, report_row.id, evidence_hash(bundle), PROMPT_VERSION, now=NOW)
    second = claim_generation_attempt(sqlite_db, report_row.id, evidence_hash(bundle), PROMPT_VERSION, now=NOW)
    assert first.claim is not None
    assert first.claim.attempt_count == 1
    assert second == ClaimDecision(claim=None, reason="recent_pending")


def test_failed_attempt_retries_until_three(sqlite_db, report_row, bundle):
    digest = evidence_hash(bundle)
    for expected in (1, 2, 3):
        decision = claim_generation_attempt(sqlite_db, report_row.id, digest, PROMPT_VERSION, now=NOW)
        assert decision.claim.attempt_count == expected
        record_generation_failure(sqlite_db, decision.claim, "invalid_json", now=NOW)
    exhausted = claim_generation_attempt(sqlite_db, report_row.id, digest, PROMPT_VERSION, now=NOW)
    assert exhausted == ClaimDecision(claim=None, reason="attempts_exhausted")


def test_stale_pending_is_reclaimed_after_fifteen_minutes(sqlite_db, report_row, bundle):
    first = claim_generation_attempt(sqlite_db, report_row.id, evidence_hash(bundle), PROMPT_VERSION, now=NOW)
    second = claim_generation_attempt(sqlite_db, report_row.id, evidence_hash(bundle), PROMPT_VERSION, now=NOW + timedelta(minutes=15))
    assert second.claim.attempt_count == 2


def test_published_and_insufficient_rows_are_terminal(sqlite_db, report_row, bundle):
    digest = evidence_hash(bundle)
    persist_insufficient_evidence(sqlite_db, report_row.id, digest, PROMPT_VERSION, now=NOW)
    assert claim_generation_attempt(sqlite_db, report_row.id, digest, PROMPT_VERSION, now=NOW).reason == "insufficient_evidence"


def test_changed_hash_gets_independent_cache_row(sqlite_db, report_row):
    first = claim_generation_attempt(sqlite_db, report_row.id, "a" * 64, PROMPT_VERSION, now=NOW)
    second = claim_generation_attempt(sqlite_db, report_row.id, "b" * 64, PROMPT_VERSION, now=NOW)
    assert first.claim.intelligence_id != second.claim.intelligence_id
```

Also test successful publication field mapping, failure clearing publish-only fields, stale rows not selected for current hash, and `load_intelligence_candidates` issuing one query for multiple report IDs.

- [ ] **Step 2: Run tests and confirm missing repository failure**

```powershell
python -m pytest tests/test_daily_report_intelligence_repository.py -q
```

Expected: collection fails because the repository does not exist.

- [ ] **Step 3: Define immutable repository return types**

```python
@dataclass(frozen=True)
class IntelligenceClaim:
    intelligence_id: UUID
    report_id: UUID
    evidence_hash: str
    prompt_version: str
    attempt_count: int


@dataclass(frozen=True)
class ClaimDecision:
    claim: IntelligenceClaim | None
    reason: str
```

- [ ] **Step 4: Implement state transitions**

Expose `get_latest_published_report`, `persist_insufficient_evidence`, `claim_generation_attempt`, `record_generation_success`, `record_generation_failure`, and `load_intelligence_candidates` with the exact arguments and return values exercised by the tests in Step 1. `load_intelligence_candidates` accepts `Sequence[UUID]` and returns `dict[UUID, list[DailyReportIntelligence]]`; the two persistence functions accept the unique cache-key fields and a required keyword-only UTC `now`.

`claim_generation_attempt` must:

1. Query the unique key.
2. Insert `pending`, `attempt_count=1`, commit, and return a detached claim when no row exists.
3. Return terminal reasons for `published`, `insufficient_evidence`, and attempt count 3.
4. Return `recent_pending` when `updated_at > now - timedelta(minutes=15)`.
5. Set retryable failed or stale-pending rows to `pending`, clear `error_code`, increment attempts, update `updated_at`, commit, and return a claim.
6. Catch `IntegrityError` from a competing insert, roll back, reload the row, and apply the same decision rules without recursion and without a provider call.

`record_generation_success` stores strings, observation texts, the per-field citation map, actual provider/model, `generated_at=now`, `status=published`, and null error. It asserts the result contains commentary. `record_generation_failure` sets `status=failed`, error code, null publish-only fields, empty JSON containers, null provider/model/generated time, updates time, and commits.

- [ ] **Step 5: Run repository tests**

```powershell
python -m pytest tests/test_daily_report_intelligence_repository.py -q
```

Expected: all claim, retry, terminal, persistence, and batch-read tests pass.

- [ ] **Step 6: Commit repository state machine**

```powershell
git add backend/app/services/daily_report_intelligence_repository.py tests/test_daily_report_intelligence_repository.py
git commit -m "feat: manage daily report intelligence attempts"
```

---

### Task 6: Orchestrate The LLM Call Across Fresh Sessions

**Files:**
- Create: `backend/app/services/daily_report_intelligence_service.py`
- Create: `tests/test_daily_report_intelligence_service.py`

- [ ] **Step 1: Write failing orchestration tests**

Use a tracking session factory whose context manager toggles `is_open`. The provider fake asserts all session contexts are closed when invoked:

```python
def test_provider_call_happens_with_no_open_session(session_factory, valid_provider):
    def assert_closed(*args, **kwargs):
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


def test_insufficient_report_never_resolves_provider(session_factory, provider_factory):
    make_latest_report(session_factory, confidence_label="low")
    outcome = run_latest_daily_report_intelligence(session_factory=session_factory, provider_factory=provider_factory, now=NOW)
    assert outcome.status == "insufficient_evidence"
    assert outcome.records_written == 1
    provider_factory.assert_not_called()


def test_same_hash_published_run_is_noop(session_factory, valid_provider):
    first = run_latest_daily_report_intelligence(session_factory=session_factory, provider_factory=lambda: valid_provider, now=NOW)
    second = run_latest_daily_report_intelligence(session_factory=session_factory, provider_factory=lambda: valid_provider, now=NOW)
    assert first.status == "published"
    assert second.status == "noop"
    assert valid_provider.generate_text_result.call_count == 1


def test_changed_report_during_call_records_stale_evidence(session_factory, mutating_provider):
    outcome = run_latest_daily_report_intelligence(session_factory=session_factory, provider_factory=lambda: mutating_provider, now=NOW)
    assert outcome.status == "failed"
    assert outcome.error_code == "stale_evidence"
```

Also test no report, provider failure, validation failure, exhausted attempts, recent pending, and an unexpected preparation exception.

- [ ] **Step 2: Run tests and confirm missing service failure**

```powershell
python -m pytest tests/test_daily_report_intelligence_service.py -q
```

Expected: collection fails because the orchestration service does not exist.

- [ ] **Step 3: Define one scheduler-facing result**

```python
@dataclass(frozen=True)
class DailyReportIntelligenceRunResult:
    status: Literal["published", "insufficient_evidence", "noop", "failed"]
    records_written: int
    report_id: str | None = None
    report_date: str | None = None
    evidence_hash: str | None = None
    prompt_version: str = PROMPT_VERSION
    attempt_count: int = 0
    error_code: str | None = None
    reason: str | None = None
```

- [ ] **Step 4: Implement the two-session workflow**

Expose `run_latest_daily_report_intelligence` with keyword-only `session_factory`, `provider_factory`, and `now` arguments. The defaults are `SessionLocal`, a factory returning `get_llm_provider_for_task("daily_report_commentary")`, and the current UTC time. The return type is `DailyReportIntelligenceRunResult`.

Implementation order is fixed:

1. Normalize `now` to UTC.
2. Open Session A, load latest published report, build bundle and hash.
3. Persist insufficient result or claim one attempt; materialize report ID/date, bundle, hash, and claim into Pydantic/dataclass values.
4. Exit Session A.
5. If no claim, return `noop` without resolving the provider.
6. Resolve provider and call `generate_daily_report_commentary` outside any session.
7. Open Session B, reload the report by claim report ID, rebuild current hash, and record `stale_evidence` if it differs.
8. Record success or typed failure and exit Session B.
9. Return the complete scheduler result without returning ORM objects.

Do not catch unexpected database exceptions inside this service; the scheduler owns unexpected run logging. Do convert provider/validation results to `status=failed` without raising.

- [ ] **Step 5: Run service tests and focused backend tests**

```powershell
python -m pytest tests/test_daily_report_intelligence_service.py tests/test_daily_report_intelligence_repository.py tests/test_daily_report_commentary.py -q
```

Expected: orchestration, repository, and validator tests pass.

- [ ] **Step 6: Commit orchestration**

```powershell
git add backend/app/services/daily_report_intelligence_service.py tests/test_daily_report_intelligence_service.py
git commit -m "feat: orchestrate daily report AI commentary"
```

---

### Task 7: Add Privacy-Safe Intelligence To Daily Report GET Responses

**Files:**
- Modify: `backend/app/schemas/daily_market_report.py`
- Modify: `backend/app/services/daily_market_report_service.py`
- Modify: `tests/test_daily_market_report_service.py`
- Modify: `tests/test_daily_market_report_api.py`

- [ ] **Step 1: Add failing public-serialization tests**

Add service tests for exact public mappings:

```python
def test_matching_published_intelligence_is_public(sqlite_db, published_report_and_intelligence):
    report = get_latest_daily_market_report(sqlite_db)
    assert report.intelligence.status == "published"
    assert report.intelligence.headline == "Pokemon market breadth improved"
    assert report.intelligence.evidence_refs == ["index:pokemon"]
    assert report.intelligence.evidence_catalog[0].source_record_id == "pokemon"
    assert report.intelligence.evidence_catalog[0].target_anchor.startswith("evidence-")
    payload = report.intelligence.model_dump()
    assert not ({"provider", "model", "attempt_count", "error_code", "evidence_hash", "prompt_version"} & payload.keys())


def test_stale_or_failed_intelligence_is_publicly_unavailable(sqlite_db, stale_intelligence):
    report = get_latest_daily_market_report(sqlite_db)
    assert report.intelligence.model_dump() == DailyReportIntelligenceResponse().model_dump()


def test_insufficient_intelligence_has_exact_public_message(sqlite_db, insufficient_intelligence):
    report = get_latest_daily_market_report(sqlite_db)
    assert report.intelligence.status == "insufficient_evidence"
    assert report.intelligence.commentary == "Insufficient evidence."
    assert report.intelligence.evidence_catalog == []


def test_history_bulk_loads_intelligence_once(sqlite_db, mocker, three_reports):
    loader = mocker.spy(daily_market_report_service, "load_intelligence_candidates")
    page = list_daily_market_reports(sqlite_db, limit=3, offset=0)
    assert len(page.reports) == 3
    loader.assert_called_once()
    assert set(loader.call_args.args[1]) == {report.id for report in three_reports}
```

Update API fixture expectations so every report includes `intelligence.status`. Add an API assertion that all registered public Daily Report routes use only `GET` and `/daily-report/generate` is absent.

- [ ] **Step 2: Run focused tests and confirm failures**

```powershell
python -m pytest tests/test_daily_market_report_service.py tests/test_daily_market_report_api.py -q
```

Expected: failures mention missing `intelligence` and loader behavior.

- [ ] **Step 3: Add the response field with a backward-compatible default**

Modify `DailyMarketReportResponse`:

```python
from pydantic import BaseModel, Field
from backend.app.schemas.daily_report_intelligence import DailyReportIntelligenceResponse


class DailyMarketReportResponse(BaseModel):
    # existing fields unchanged
    intelligence: DailyReportIntelligenceResponse = Field(default_factory=DailyReportIntelligenceResponse)
```

- [ ] **Step 4: Implement current-hash public selection**

Add `_public_intelligence(row, candidates) -> DailyReportIntelligenceResponse` and extend `_response_from_row(row, intelligence_candidates=()) -> DailyMarketReportResponse`. The candidate argument is a `Sequence[DailyReportIntelligence]` and defaults to an empty tuple.

`_public_intelligence` rebuilds the current bundle/hash and chooses only `(current_hash, PROMPT_VERSION)`. Map pending, failed, and missing to the default unavailable object. Map insufficient to the exact message and empty arrays. For published rows:

1. Reconstruct observations by zipping `key_observations_json` with `evidence_refs_json["key_observations"]`.
2. Flatten references in headline, commentary, observations, risk order while preserving first occurrence.
3. Select only referenced bundle records for the catalog, preserving canonical bundle order.
4. Copy each selected record's `source_record_id` unchanged into the catalog. Public catalog items contain only `id`, `kind`, `label`, `source_record_id`, and `target_anchor`; do not expose record facts or `source_url` through this catalog.
5. Never include internal columns.

Update latest and dated reads to call `load_intelligence_candidates` once for their one report ID. Update history to call it once for all page IDs and pass the mapped candidate list into `_response_from_row`.

- [ ] **Step 5: Run service and API tests**

```powershell
python -m pytest tests/test_daily_market_report_service.py tests/test_daily_market_report_api.py -q
```

Expected: all response states, privacy checks, batch loading, and GET-only tests pass.

- [ ] **Step 6: Commit public API integration**

```powershell
git add backend/app/schemas/daily_market_report.py backend/app/services/daily_market_report_service.py tests/test_daily_market_report_service.py tests/test_daily_market_report_api.py
git commit -m "feat: expose safe daily report intelligence"
```

---

### Task 8: Register The Feature-Flagged Hourly Scheduler Job

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `.env.example`
- Modify: `backend/app/services/scheduler_run_log_service.py`
- Modify: `backend/app/backstage/scheduler.py`
- Modify: `tests/test_daily_market_report_scheduler.py`
- Modify: `tests/test_scheduler_startup.py`

- [ ] **Step 1: Write failing configuration and scheduler tests**

Add tests:

```python
def test_register_daily_report_intelligence_job_uses_configured_interval():
    scheduler = MagicMock()
    settings = SimpleNamespace(daily_report_ai_interval_minutes=60)
    _register_daily_report_intelligence_job(scheduler, settings)
    call_args = scheduler.add_job.call_args
    assert call_args.args[1] == "interval"
    assert call_args.kwargs == {
        "minutes": 60,
        "id": JOB_DAILY_REPORT_INTELLIGENCE,
        "replace_existing": True,
        "max_instances": 1,
        "coalesce": True,
        "next_run_time": None,
    }


def test_build_scheduler_skips_ai_job_when_disabled(mocker):
    import backend.app.backstage.scheduler as scheduler_module
    settings = scheduler_module.get_settings().model_copy(update={"daily_report_ai_enabled": False})
    mocker.patch.object(scheduler_module, "get_settings", return_value=settings)
    register = mocker.patch.object(scheduler_module, "_register_daily_report_intelligence_job")
    built = scheduler_module.build_scheduler()
    register.assert_not_called()


def test_build_scheduler_registers_ai_job_when_enabled(mocker):
    import backend.app.backstage.scheduler as scheduler_module
    settings = scheduler_module.get_settings().model_copy(
        update={"daily_report_ai_enabled": True, "daily_report_ai_interval_minutes": 45}
    )
    mocker.patch.object(scheduler_module, "get_settings", return_value=settings)
    register = mocker.patch.object(scheduler_module, "_register_daily_report_intelligence_job")
    built = scheduler_module.build_scheduler()
    register.assert_called_once_with(built, settings)


@pytest.mark.parametrize(
    ("service_result", "expected_status", "records_written", "errors"),
    [
        (DailyReportIntelligenceRunResult(status="published", records_written=1), "success", 1, 0),
        (DailyReportIntelligenceRunResult(status="insufficient_evidence", records_written=1), "success", 1, 0),
        (DailyReportIntelligenceRunResult(status="noop", records_written=0, reason="already_published"), "success", 0, 0),
        (DailyReportIntelligenceRunResult(status="failed", records_written=0, error_code="invalid_json"), "error", 0, 1),
    ],
)
def test_ai_job_maps_service_result_to_run_log(service_result, expected_status, records_written, errors):
    start_session = MagicMock(name="start_session")
    log_session = MagicMock(name="log_session")
    start_context = MagicMock()
    start_context.__enter__.return_value = start_session
    start_context.__exit__.return_value = False
    log_context = MagicMock()
    log_context.__enter__.return_value = log_session
    log_context.__exit__.return_value = False
    with (
        patch("backend.app.backstage.scheduler.SessionLocal", side_effect=[start_context, log_context]),
        patch("backend.app.backstage.scheduler.start_run", return_value=41),
        patch("backend.app.backstage.scheduler.run_latest_daily_report_intelligence", return_value=service_result),
        patch("backend.app.backstage.scheduler.finish_run") as finish,
        patch("backend.app.backstage.scheduler.prune_old_runs") as prune,
    ):
        _run_daily_report_intelligence()
    assert finish.call_args.args == (log_session, 41)
    assert finish.call_args.kwargs["status"] == expected_status
    assert finish.call_args.kwargs["records_written"] == records_written
    assert finish.call_args.kwargs["errors"] == errors
    prune.assert_called_once_with(log_session, JOB_DAILY_REPORT_INTELLIGENCE)
```

The run-log test uses two separate scheduler logging contexts. `tests/test_daily_report_intelligence_service.py` separately proves that the service's preparation and publishing sessions are closed around the provider call.

- [ ] **Step 2: Run scheduler tests and confirm failures**

```powershell
python -m pytest tests/test_daily_market_report_scheduler.py tests/test_scheduler_startup.py -q
```

Expected: failures mention missing settings, job constant, registration, and runner.

- [ ] **Step 3: Add configuration and operator documentation**

Add to `Settings`:

```python
daily_report_ai_enabled: bool = False
daily_report_ai_interval_minutes: int = Field(default=60, ge=15)
```

Add to `.env.example` beneath provider settings:

```dotenv
# Daily Report AI commentary. Keep disabled until staging verification passes.
DAILY_REPORT_AI_ENABLED=false
DAILY_REPORT_AI_INTERVAL_MINUTES=60
```

Also correct the existing provider comment to list `anthropic`, `groq`, and `openai` if it is still stale after rebasing.

- [ ] **Step 4: Add the job constant, runner, and registration**

Add `JOB_DAILY_REPORT_INTELLIGENCE = "daily-report-intelligence"` to the run-log service, import it in the scheduler, import `run_latest_daily_report_intelligence` from its service module, and add startup delay `1380`.

Implement:

```python
def _run_daily_report_intelligence() -> None:
    with SessionLocal() as start_session:
        run_id = start_run(start_session, JOB_DAILY_REPORT_INTELLIGENCE)
    try:
        result = run_latest_daily_report_intelligence()
        status = "error" if result.status == "failed" else "success"
        errors = 1 if result.status == "failed" else 0
        error_message = result.error_code if result.status == "failed" else None
        meta = {
            "report_id": result.report_id,
            "report_date": result.report_date,
            "evidence_hash": result.evidence_hash,
            "prompt_version": result.prompt_version,
            "intelligence_status": result.status,
            "attempt_count": result.attempt_count,
            "error_code": result.error_code,
            "reason": result.reason,
        }
    except Exception as exc:
        logger.exception("daily-report-intelligence job failed")
        status, errors, error_message, meta = "error", 1, str(exc), {"error_code": "internal_error"}
        result = DailyReportIntelligenceRunResult(status="failed", records_written=0, error_code="internal_error")
    with SessionLocal() as log_session:
        finish_run(log_session, run_id, status=status, records_written=result.records_written, errors=errors, error_message=error_message, meta_json=meta)
        prune_old_runs(log_session, JOB_DAILY_REPORT_INTELLIGENCE)
```

Implement `_register_daily_report_intelligence_job(scheduler, settings)` with the kwargs asserted above. In `build_scheduler`, call it only when `settings.daily_report_ai_enabled`; otherwise log that commentary generation is disabled. Keep deterministic Daily Report registration unconditional.

- [ ] **Step 5: Run scheduler and configuration tests**

```powershell
python -m pytest tests/test_daily_market_report_scheduler.py tests/test_scheduler_startup.py tests/test_scheduler_run_log_cleanup.py -q
```

Expected: registration, run-result mapping, fresh-session logging, and existing scheduler cleanup tests pass.

- [ ] **Step 6: Commit scheduler integration**

```powershell
git add backend/app/core/config.py .env.example backend/app/services/scheduler_run_log_service.py backend/app/backstage/scheduler.py tests/test_daily_market_report_scheduler.py tests/test_scheduler_startup.py
git commit -m "feat: schedule daily report AI commentary"
```

---

### Task 9: Add Frontend Types And Shared Evidence Links

**Files:**
- Modify: `frontend/src/types/api.ts`
- Create: `frontend/src/components/DailyReportEvidenceLinks.tsx`
- Create: `frontend/src/components/DailyReportEvidenceLinks.test.tsx`
- Modify: `frontend/src/pages/DashboardPage.test.tsx`
- Modify: `frontend/src/pages/DailyReportDetailPage.test.tsx`
- Modify: `frontend/src/pages/DailyReportsPage.test.tsx`

- [ ] **Step 1: Write failing citation-component tests**

```tsx
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import DailyReportEvidenceLinks from './DailyReportEvidenceLinks'

const catalog = [
  { id: 'index:pokemon', kind: 'index' as const, label: 'Pokemon Market', source_record_id: 'pokemon', target_anchor: 'evidence-abc123abc123' },
]

it('links known evidence to the dated report anchor', () => {
  render(<MemoryRouter><DailyReportEvidenceLinks reportDate="2026-07-22" refs={['index:pokemon']} catalog={catalog} /></MemoryRouter>)
  expect(screen.getByRole('link', { name: 'Evidence 1: Pokemon Market' }).getAttribute('href'))
    .toBe('/reports/2026-07-22#evidence-abc123abc123')
})

it('omits unknown references instead of creating a broken link', () => {
  render(<MemoryRouter><DailyReportEvidenceLinks reportDate="2026-07-22" refs={['index:missing']} catalog={catalog} /></MemoryRouter>)
  expect(screen.queryByRole('link')).toBeNull()
})
```

- [ ] **Step 2: Run the component test and confirm failure**

```powershell
Set-Location frontend
npm test -- --run src/components/DailyReportEvidenceLinks.test.tsx
```

Expected: TypeScript or module resolution fails because types/component do not exist.

- [ ] **Step 3: Add exact TypeScript API types**

Add:

```typescript
export type DailyReportIntelligenceStatus = 'published' | 'insufficient_evidence' | 'unavailable'
export type DailyReportEvidenceKind = 'index' | 'mover' | 'signal' | 'catalyst' | 'report_evidence'

export interface DailyReportIntelligenceObservation {
  text: string
  evidence_refs: string[]
}

export interface DailyReportEvidenceCatalogItem {
  id: string
  kind: DailyReportEvidenceKind
  label: string
  source_record_id: string | null
  target_anchor: string
}

export interface DailyReportIntelligence {
  status: DailyReportIntelligenceStatus
  headline: string | null
  commentary: string | null
  risk_summary: string | null
  key_observations: DailyReportIntelligenceObservation[]
  evidence_refs: string[]
  evidence_catalog: DailyReportEvidenceCatalogItem[]
  generated_at: string | null
}
```

Add `intelligence: DailyReportIntelligence` to `DailyMarketReport`.

Add this required unavailable value to every existing typed `DailyMarketReport` fixture in `DashboardPage.test.tsx`, `DailyReportDetailPage.test.tsx`, and `DailyReportsPage.test.tsx` in the same step:

```typescript
intelligence: {
  status: 'unavailable',
  headline: null,
  commentary: null,
  risk_summary: null,
  key_observations: [],
  evidence_refs: [],
  evidence_catalog: [],
  generated_at: null,
},
```

- [ ] **Step 4: Implement the shared link component**

Create a component that builds a `Map(catalog.map(item => [item.id, item]))`, keeps reference order, removes duplicate refs, skips missing catalog records, and renders at most the caller's optional `limit`:

```tsx
interface Props {
  reportDate: string
  refs: string[]
  catalog: DailyReportEvidenceCatalogItem[]
  limit?: number
}

export default function DailyReportEvidenceLinks({ reportDate, refs, catalog, limit }: Props) {
  const byId = new Map(catalog.map(item => [item.id, item]))
  const resolved = Array.from(new Set(refs)).map(id => byId.get(id)).filter((item): item is DailyReportEvidenceCatalogItem => item !== undefined)
  const visible = limit === undefined ? resolved : resolved.slice(0, limit)
  if (visible.length === 0) return null
  return (
    <span className="daily-report-ai-citations" aria-label="Supporting evidence">
      {visible.map((item, index) => (
        <Link key={item.id} to={`/reports/${reportDate}#${item.target_anchor}`}>
          Evidence {index + 1}: {item.label}
        </Link>
      ))}
    </span>
  )
}
```

- [ ] **Step 5: Run types and component tests**

```powershell
npm test -- --run src/components/DailyReportEvidenceLinks.test.tsx
npm run build
```

Expected: component tests and TypeScript production build pass. Existing report fixtures may now fail in later page tests until Tasks 10 and 11 update them; the build must still pass because test fixtures are not part of the build.

- [ ] **Step 6: Commit frontend contract**

```powershell
Set-Location ..
git add frontend/src/types/api.ts frontend/src/components/DailyReportEvidenceLinks.tsx frontend/src/components/DailyReportEvidenceLinks.test.tsx frontend/src/pages/DashboardPage.test.tsx frontend/src/pages/DailyReportDetailPage.test.tsx frontend/src/pages/DailyReportsPage.test.tsx
git commit -m "feat: add daily report intelligence client types"
```

---

### Task 10: Render Published Commentary On The Dashboard

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/pages/DashboardPage.test.tsx`
- Modify: `frontend/src/styles/theme.css`

- [ ] **Step 1: Extract a reusable Dashboard report fixture**

Import `DailyMarketReport` and move the existing inline `fetchLatestDailyMarketReport` response into `makeDailyReportFixture(): DailyMarketReport`. Preserve every existing field and the unavailable intelligence object added in Task 9. Change `beforeEach` to:

```typescript
vi.mocked(fetchLatestDailyMarketReport).mockResolvedValue(makeDailyReportFixture())
```

- [ ] **Step 2: Write failing Dashboard behavior tests**

```tsx
it('shows published AI commentary with up to three evidence links', async () => {
  const report = makeDailyReportFixture()
  report.intelligence = {
    status: 'published',
    headline: 'Pokemon market breadth improved',
    commentary: 'The captured Pokemon index moved higher.',
    risk_summary: 'Coverage remains limited.',
    key_observations: [],
    evidence_refs: ['index:pokemon'],
    evidence_catalog: [{ id: 'index:pokemon', kind: 'index', label: 'Pokemon Market', source_record_id: 'pokemon', target_anchor: 'evidence-abc123abc123' }],
    generated_at: '2026-07-22T01:00:00Z',
  }
  vi.mocked(fetchLatestDailyMarketReport).mockResolvedValueOnce(report)
  renderDashboard()
  const panel = await screen.findByRole('region', { name: 'Flashcard Planet Daily' })
  expect(within(panel).getByText('Pokemon market breadth improved')).toBeTruthy()
  expect(within(panel).getByText('The captured Pokemon index moved higher.')).toBeTruthy()
  expect(within(panel).queryByText(report.summary)).toBeNull()
  expect(within(panel).getByRole('link', { name: 'Evidence 1: Pokemon Market' }).getAttribute('href'))
    .toBe('/reports/2026-07-21#evidence-abc123abc123')
})

it.each(['insufficient_evidence', 'unavailable'] as const)(
  'keeps the deterministic summary when intelligence is %s',
  async status => {
    const report = makeDailyReportFixture()
    report.intelligence.status = status
    report.intelligence.commentary = status === 'insufficient_evidence' ? 'Insufficient evidence.' : null
    vi.mocked(fetchLatestDailyMarketReport).mockResolvedValueOnce(report)
    renderDashboard()
    const panel = await screen.findByRole('region', { name: 'Flashcard Planet Daily' })
    expect(within(panel).getByText(report.summary)).toBeTruthy()
    expect(within(panel).queryByLabelText('Supporting evidence')).toBeNull()
  },
)
```

- [ ] **Step 3: Run Dashboard tests and confirm failure**

```powershell
Set-Location frontend
npm test -- --run src/pages/DashboardPage.test.tsx
```

Expected: published headline/commentary and citation assertions fail.

- [ ] **Step 4: Implement published/fallback rendering**

In `DailyMarketReportPanel`, derive:

```typescript
const hasPublishedIntelligence = report.intelligence.status === 'published'
  && report.intelligence.headline !== null
  && report.intelligence.commentary !== null
const summary = hasPublishedIntelligence ? report.intelligence.commentary : report.summary
```

When published, render the headline above `summary` and render `DailyReportEvidenceLinks` with `limit={3}`. Otherwise preserve the current summary and deterministic evidence list exactly. Do not show `Insufficient evidence.` on the Dashboard and do not change loading, missing-report, or request-error states.

- [ ] **Step 5: Add restrained Dashboard styles and run tests**

Add CSS classes for `.daily-report-ai-headline` and `.daily-report-ai-citations`; use existing text, gold, border, font, and focus tokens. Links wrap rather than overflow and have a visible `:focus-visible` outline.

Run:

```powershell
npm test -- --run src/pages/DashboardPage.test.tsx src/components/DailyReportEvidenceLinks.test.tsx
npm run build
```

Expected: tests and build pass.

- [ ] **Step 6: Commit Dashboard experience**

```powershell
Set-Location ..
git add frontend/src/pages/DashboardPage.tsx frontend/src/pages/DashboardPage.test.tsx frontend/src/styles/theme.css
git commit -m "feat: show AI commentary on dashboard reports"
```

---

### Task 11: Add The Detail Commentary Section And Evidence Anchors

**Files:**
- Modify: `frontend/src/pages/DailyReportDetailPage.tsx`
- Modify: `frontend/src/pages/DailyReportDetailPage.test.tsx`
- Modify: `frontend/src/styles/theme.css`

- [ ] **Step 1: Confirm the detail fixture has the required default**

Confirm Task 9 added the unavailable intelligence object to `makeReport()`. Keep it as the default for every pre-existing detail test. Import `DailyReportIntelligence` and `DailyReportEvidenceKind`, then add these helpers so all new test references are defined:

```typescript
function makePublishedIntelligence(
  overrides: Partial<DailyReportIntelligence> = {},
): DailyReportIntelligence {
  return {
    status: 'published',
    headline: 'Pokemon market breadth improved',
    commentary: 'The captured Pokemon index moved 4.25%.',
    risk_summary: 'Coverage includes 4 observed assets.',
    key_observations: [
      { text: 'Charizard moved 20%.', evidence_refs: ['mover:asset-charizard'] },
    ],
    evidence_refs: ['index:pokemon', 'mover:asset-charizard'],
    evidence_catalog: [
      { id: 'index:pokemon', kind: 'index', label: 'Pokemon Market', source_record_id: 'pokemon', target_anchor: 'evidence-index000001' },
      { id: 'mover:asset-charizard', kind: 'mover', label: 'Charizard', source_record_id: 'asset-charizard', target_anchor: 'evidence-mover000001' },
    ],
    generated_at: '2026-07-22T01:00:00Z',
    ...overrides,
  }
}

function makeReportWithCatalogForEveryKind(): DailyMarketReport {
  const report = makeReport()
  const catalyst = makeCatalyst()
  report.catalysts = [catalyst]
  report.intelligence = makePublishedIntelligence({
    evidence_refs: [
      'index:pokemon',
      'mover:asset-charizard',
      'signal:breakout',
      `catalyst:${catalyst.id}`,
      'report:evidence:2',
    ],
    evidence_catalog: [
      { id: 'index:pokemon', kind: 'index', label: 'Pokemon Market', source_record_id: 'pokemon', target_anchor: 'evidence-index000001' },
      { id: 'mover:asset-charizard', kind: 'mover', label: 'Charizard', source_record_id: 'asset-charizard', target_anchor: 'evidence-mover000001' },
      { id: 'signal:breakout', kind: 'signal', label: 'BREAKOUT', source_record_id: 'BREAKOUT', target_anchor: 'evidence-signal00001' },
      { id: `catalyst:${catalyst.id}`, kind: 'catalyst', label: catalyst.description, source_record_id: catalyst.id, target_anchor: 'evidence-catalyst001' },
      { id: 'report:evidence:2', kind: 'report_evidence', label: 'market_segment=raw', source_record_id: null, target_anchor: 'evidence-report00001' },
    ],
  })
  return report
}
```

- [ ] **Step 2: Write failing detail tests**

Add `waitFor` to the Testing Library imports before adding the focus assertion.

```tsx
it('renders published AI commentary, observations, risk, and local citations', async () => {
  const report = makeReport()
  report.intelligence = makePublishedIntelligence()
  vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(report)
  renderPage()
  const section = await screen.findByRole('region', { name: 'AI Market Commentary' })
  expect(within(section).getByRole('heading', { name: report.intelligence.headline! })).toBeTruthy()
  expect(within(section).getByText(report.intelligence.commentary!)).toBeTruthy()
  expect(within(section).getByText(report.intelligence.key_observations[0].text)).toBeTruthy()
  expect(within(section).getByText(report.intelligence.risk_summary!)).toBeTruthy()
})


it('shows exact neutral text for insufficient evidence', async () => {
  const report = makeReport()
  report.intelligence.status = 'insufficient_evidence'
  report.intelligence.commentary = 'Insufficient evidence.'
  vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(report)
  renderPage()
  expect(await screen.findByText('Insufficient evidence.')).toBeTruthy()
})


it('omits AI section when intelligence is unavailable', async () => {
  vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(makeReport())
  renderPage()
  await screen.findByRole('heading', { name: 'Flashcard Planet Daily - 2026-07-21' })
  expect(screen.queryByRole('region', { name: 'AI Market Commentary' })).toBeNull()
})


it('assigns server-provided anchors to every evidence target', async () => {
  const report = makeReportWithCatalogForEveryKind()
  vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(report)
  const { container } = renderPage()
  await screen.findByRole('region', { name: 'AI Market Commentary' })
  for (const item of report.intelligence.evidence_catalog) {
    const target = container.querySelector(`#${item.target_anchor}`)
    expect(target).not.toBeNull()
    expect(target?.getAttribute('tabindex')).toBe('-1')
  }
})


it('matches Unicode rows through exact server source IDs without reconstructing evidence IDs', async () => {
  const report = makeReportWithCatalogForEveryKind()
  report.overview.indexes[0].game = 'Pok\u00e9mon'
  report.overview.indexes[0].label = 'Pok\u00e9mon Market'
  const catalogItem = report.intelligence.evidence_catalog.find(item => item.kind === 'index')!
  catalogItem.id = 'index:pokemon'
  catalogItem.label = 'Pok\u00e9mon Market'
  catalogItem.source_record_id = 'Pok\u00e9mon'
  vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(report)
  const { container } = renderPage()
  await screen.findByRole('region', { name: 'AI Market Commentary' })
  const target = container.querySelector(`#${catalogItem.target_anchor}`)
  expect(target?.textContent).toContain('Pok\u00e9mon Market')
})


it('focuses the cited target when the report route has an evidence fragment', async () => {
  const report = makeReportWithCatalogForEveryKind()
  vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(report)
  renderPage('/reports/2026-07-21#evidence-index000001')
  await waitFor(() => expect(document.activeElement?.id).toBe('evidence-index000001'))
})


it('renders model-looking markup as plain text', async () => {
  const report = makeReport()
  report.intelligence = makePublishedIntelligence({ commentary: '<strong>Observed</strong> **market**' })
  vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(report)
  const { container } = renderPage()
  expect(await screen.findByText('<strong>Observed</strong> **market**')).toBeTruthy()
  expect(container.querySelector('strong')?.textContent).not.toBe('Observed')
})
```

- [ ] **Step 3: Run detail tests and confirm failure**

```powershell
Set-Location frontend
npm test -- --run src/pages/DailyReportDetailPage.test.tsx
```

Expected: AI section and anchor assertions fail.

- [ ] **Step 4: Implement evidence-target lookup and AI section**

Allow the test helper to accept an initial entry, defaulting to the current dated path. Add `useLocation` to the React Router imports. In `DailyReportContent`, resolve targets directly from the exact server-provided catalog source keys:

```typescript
const evidenceCatalog = report.intelligence.evidence_catalog

const targetPropsForSource = (
  kind: DailyReportEvidenceKind,
  sourceRecordId: string,
) => {
  const item = evidenceCatalog.find(
    candidate => candidate.kind === kind && candidate.source_record_id === sourceRecordId,
  )
  return item === undefined ? {} : { id: item.target_anchor, tabIndex: -1 }
}

const targetPropsForExactLabel = (
  kind: DailyReportEvidenceKind,
  label: string,
) => {
  const item = evidenceCatalog.find(
    candidate => (
      candidate.kind === kind
      && candidate.source_record_id === null
      && candidate.label === label
    ),
  )
  return item === undefined ? {} : { id: item.target_anchor, tabIndex: -1 }
}
```

Apply `targetPropsForSource` with the row's exact public source value: `('index', index.game)`, `('mover', mover.asset_id)`, `('signal', signal.label)`, and `('catalyst', catalyst.id)`. Do not lowercase, normalize, transliterate, hash, prefix, or otherwise reconstruct an evidence ID in the frontend. The catalog's `id` remains the server-owned citation reference used by `DailyReportEvidenceLinks`; detail target lookup uses only exact `(kind, source_record_id)`.

For report evidence, whose catalog entries intentionally have `source_record_id: null`, use `targetPropsForExactLabel('report_evidence', label)` and apply the returned anchor only to the first list item with that exact label so duplicate source statements never create duplicate DOM IDs. Add `daily-report-evidence-target` alongside each target's existing class instead of replacing existing classes. Every DOM `id` comes unchanged from the matched catalog item's `target_anchor`.

Use `useLocation` and a focused effect to handle both initial fragments and citation clicks:

```typescript
const location = useLocation()

useEffect(() => {
  if (!location.hash) return undefined
  const frame = window.requestAnimationFrame(() => {
    const target = document.getElementById(location.hash.slice(1))
    if (target === null) return
    target.focus({ preventScroll: true })
    target.scrollIntoView({ block: 'center' })
  })
  return () => window.cancelAnimationFrame(frame)
}, [location.hash, report.id])
```

Insert an unframed `<section aria-label="AI Market Commentary">` immediately after the hero:

- Published: headline, commentary, each observation with its own `DailyReportEvidenceLinks`, risk summary with its citations.
- Insufficient: section heading and exact `Insufficient evidence.` text.
- Unavailable: return `null` for the entire AI section.

All model text remains React text children. Do not use a Markdown package or `dangerouslySetInnerHTML`.

- [ ] **Step 5: Add focus, spacing, and mobile styles**

Add:

```css
.daily-report-evidence-target {
  scroll-margin-top: 88px;
}

.daily-report-evidence-target:focus {
  outline: 2px solid var(--gold);
  outline-offset: 3px;
}

.daily-report-ai-section {
  padding: 24px 0;
  border-bottom: 1px solid var(--border-subtle);
}

.daily-report-ai-observations {
  display: grid;
  gap: 12px;
  margin: 18px 0;
  padding: 0;
  list-style: none;
}
```

At `max-width: 640px`, stack citation links and let all commentary text wrap with `overflow-wrap: anywhere`; do not introduce horizontal scrolling or nested cards.

- [ ] **Step 6: Run all Daily Report frontend tests and build**

```powershell
npm test -- --run src/components/DailyReportEvidenceLinks.test.tsx src/pages/DashboardPage.test.tsx src/pages/DailyReportDetailPage.test.tsx src/pages/DailyReportsPage.test.tsx src/api/api.test.ts
npm run lint -- --quiet
npm run build
```

Expected: selected tests, lint, and production build pass.

- [ ] **Step 7: Commit detail experience**

```powershell
Set-Location ..
git add frontend/src/pages/DailyReportDetailPage.tsx frontend/src/pages/DailyReportDetailPage.test.tsx frontend/src/styles/theme.css
git commit -m "feat: add evidence-linked report intelligence"
```

---

### Task 12: Verify Migration, Security, Compatibility, And Visual Quality

**Files:**
- Modify: `docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md`
- Verify: all changed files

- [ ] **Step 1: Run the complete focused backend set**

```powershell
python -m pytest tests/test_daily_report_intelligence_migration.py tests/test_daily_report_evidence.py tests/test_daily_report_commentary.py tests/test_daily_report_intelligence_repository.py tests/test_daily_report_intelligence_service.py tests/test_daily_market_report_service.py tests/test_daily_market_report_api.py tests/test_daily_market_report_scheduler.py tests/test_scheduler_startup.py tests/test_llm_provider.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run security and source scans**

```powershell
rg -n "daily-report/generate" backend tests frontend
rg -n "dangerouslySetInnerHTML|react-markdown|marked" frontend/src
rg -n "raw.*response|provider.*response|system_prompt|user_prompt" backend/app/services/daily_report_*.py backend/app/backstage/scheduler.py
```

Expected: no public generate route, no model-content HTML/Markdown rendering, and no raw response or complete prompt persistence/logging. Prompt-building variable names inside the commentary service are allowed; log or model columns containing those values are not.

- [ ] **Step 3: Run the full backend suite**

```powershell
python -m pytest tests -q
```

Expected: all tests pass. If a failure appears unrelated, reproduce it on the untouched merged-main commit before documenting it; do not dismiss a new failure as pre-existing without that reproduction.

- [ ] **Step 4: Verify migration round trip against disposable PostgreSQL 16**

Use the repository's existing disposable PostgreSQL procedure, including pgvector installation when required by migration `0038`:

```powershell
alembic upgrade head
alembic downgrade 0042
alembic upgrade head
alembic current
```

Expected: all commands succeed and `alembic current` reports `0043 (head)`. Inspect PostgreSQL metadata to confirm the foreign key, unique constraint, two check constraints, and both indexes.

- [ ] **Step 5: Run the complete frontend suite**

```powershell
Set-Location frontend
npm test
npm run lint
npm run build
```

Expected: all frontend tests, lint, and build pass.

- [ ] **Step 6: Perform desktop and mobile browser QA**

Start the backend and frontend with AI disabled. Open the Dashboard and `/reports/<latest-date>` at approximately 1440x900 and 375x812. Verify:

- deterministic report works with `DAILY_REPORT_AI_ENABLED=false`;
- published fixture/staging commentary wraps and citations navigate to visible focused targets;
- insufficient commentary is neutral on detail and falls back on Dashboard;
- unavailable intelligence leaves the report complete;
- there is no overlap, clipping, blank content, layout shift, or horizontal scrolling;
- browser console has no errors.

Capture screenshots for both viewports and inspect them before continuing.

- [ ] **Step 7: Update execution evidence**

In `docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md`, mark Phase 5 Daily Report AI Commentary as complete only after Steps 1-6 pass. Record exact test counts, migration round trip, feature-flag state, build result, and desktop/mobile QA. Do not claim provider production success until a staging provider call has actually published a validated row.

- [ ] **Step 8: Run final repository checks**

```powershell
Set-Location ..
git diff --check
git status --short
git log --oneline --decorate -12
```

Expected: no whitespace errors; only the intended documentation update remains uncommitted.

- [ ] **Step 9: Commit verification evidence**

```powershell
git add docs/flashcard-planet-v2/CODEX_EXECUTION_PLAN.md
git commit -m "docs: record daily report AI verification"
```

- [ ] **Step 10: Request final code review before publishing the branch**

Invoke `superpowers:requesting-code-review`. Resolve every blocking or important finding, rerun the affected tests, then use `superpowers:verification-before-completion` before pushing and opening a Draft PR.

Final acceptance evidence must demonstrate:

1. No LLM call for insufficient evidence.
2. No duplicate call for a published cache key.
3. No database session open during provider execution.
4. No invented number or unknown citation reaches the API.
5. No private generation metadata reaches the API.
6. All Daily Report public routes remain GET-only.
7. Dashboard and detail deterministic fallbacks remain usable.
8. Full automated, migration, build, and browser verification is current.
