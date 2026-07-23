from __future__ import annotations

import importlib
import importlib.util
import uuid
from pathlib import Path
from unittest.mock import MagicMock, call

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


TABLE_NAME = "daily_report_intelligence"
EXPECTED_COLUMNS = [
    "id",
    "report_id",
    "evidence_hash",
    "prompt_version",
    "status",
    "headline",
    "commentary",
    "risk_summary",
    "key_observations_json",
    "evidence_refs_json",
    "provider",
    "model",
    "attempt_count",
    "error_code",
    "generated_at",
    "created_at",
    "updated_at",
]
CACHE_KEY_COLUMNS = ["report_id", "evidence_hash", "prompt_version"]
STATUS_CONDITION = (
    "status IN ('pending', 'published', 'insufficient_evidence', 'failed')"
)
ATTEMPT_COUNT_CONDITION = "attempt_count BETWEEN 0 AND 3"


def _load_model():
    module = importlib.import_module("backend.app.models.daily_report_intelligence")
    return module.DailyReportIntelligence


def _load_migration():
    path = (
        Path(__file__).parent.parent
        / "migrations"
        / "versions"
        / "0043_add_daily_report_intelligence.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0043", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    migration.op = MagicMock()
    return migration


def _upgrade_table_args(migration):
    migration.upgrade()
    migration.op.create_table.assert_called_once()
    return migration.op.create_table.call_args.args


def test_model_exports_exact_columns():
    model = _load_model()
    models_package = importlib.import_module("backend.app.models")

    assert model.__tablename__ == TABLE_NAME
    assert list(model.__table__.columns.keys()) == EXPECTED_COLUMNS
    assert models_package.DailyReportIntelligence is model
    assert "DailyReportIntelligence" in models_package.__all__


def test_model_defines_cache_constraints_and_indexes():
    model = _load_model()
    table = model.__table__

    unique_constraints = [
        constraint
        for constraint in table.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    ]
    assert [
        (constraint.name, list(constraint.columns.keys()))
        for constraint in unique_constraints
    ] == [("uq_daily_report_intelligence_cache_key", CACHE_KEY_COLUMNS)]

    check_constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, sa.CheckConstraint)
    }
    assert check_constraints == {
        "ck_daily_report_intelligence_status": STATUS_CONDITION,
        "ck_daily_report_intelligence_attempt_count": ATTEMPT_COUNT_CONDITION,
    }

    indexes = {
        index.name: tuple(column.name for column in index.columns)
        for index in table.indexes
    }
    assert indexes == {
        "ix_daily_report_intelligence_report_id": ("report_id",),
        "ix_daily_report_intelligence_status_updated": ("status", "updated_at"),
    }


def test_model_defines_required_types_defaults_and_foreign_key():
    model = _load_model()
    columns = model.__table__.c

    assert isinstance(columns.id.type, UUID)
    assert isinstance(columns.id.default.arg(None), uuid.UUID)
    report_foreign_key = next(iter(columns.report_id.foreign_keys))
    assert report_foreign_key.target_fullname == "daily_market_reports.id"
    assert report_foreign_key.ondelete == "CASCADE"

    assert columns.evidence_hash.type.length == 64
    assert columns.prompt_version.type.length == 64
    assert columns.status.type.length == 32
    assert isinstance(columns.key_observations_json.type, JSONB)
    assert columns.key_observations_json.default.arg(None) == []
    assert isinstance(columns.evidence_refs_json.type, JSONB)
    assert columns.evidence_refs_json.default.arg(None) == {}
    assert columns.provider.type.length == 32
    assert columns.model.type.length == 128
    assert columns.attempt_count.default.arg == 0
    assert columns.error_code.type.length == 64
    assert columns.generated_at.type.timezone is True
    assert columns.created_at.type.timezone is True
    assert columns.created_at.server_default is not None
    assert columns.updated_at.type.timezone is True
    assert columns.updated_at.server_default is not None
    assert columns.updated_at.onupdate is not None

    nullable_columns = {
        "headline",
        "commentary",
        "risk_summary",
        "provider",
        "model",
        "error_code",
        "generated_at",
    }
    assert {
        column.name for column in columns if column.nullable
    } == nullable_columns


def test_upgrade_creates_exactly_the_daily_report_intelligence_table():
    migration = _load_migration()

    table_args = _upgrade_table_args(migration)

    assert table_args[0] == TABLE_NAME
    assert migration.op.create_table.call_count == 1


def test_upgrade_table_has_required_columns_defaults_and_constraints():
    migration = _load_migration()

    table_args = _upgrade_table_args(migration)
    columns = {
        item.name: item for item in table_args[1:] if isinstance(item, sa.Column)
    }
    constraints = [
        item for item in table_args[1:] if isinstance(item, sa.Constraint)
    ]

    assert list(columns) == EXPECTED_COLUMNS
    assert str(columns["key_observations_json"].server_default.arg) == "'[]'::jsonb"
    assert str(columns["evidence_refs_json"].server_default.arg) == "'{}'::jsonb"
    assert str(columns["attempt_count"].server_default.arg) == "0"
    report_foreign_key = next(iter(columns["report_id"].foreign_keys))
    assert report_foreign_key.target_fullname == "daily_market_reports.id"
    assert report_foreign_key.ondelete == "CASCADE"

    unique_constraint = next(
        item for item in constraints if isinstance(item, sa.UniqueConstraint)
    )
    assert unique_constraint.name == "uq_daily_report_intelligence_cache_key"
    assert list(unique_constraint._pending_colargs) == CACHE_KEY_COLUMNS

    check_constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in constraints
        if isinstance(constraint, sa.CheckConstraint)
    }
    assert check_constraints == {
        "ck_daily_report_intelligence_status": STATUS_CONDITION,
        "ck_daily_report_intelligence_attempt_count": ATTEMPT_COUNT_CONDITION,
    }


def test_upgrade_creates_required_indexes():
    migration = _load_migration()

    migration.upgrade()

    assert migration.op.create_index.call_args_list == [
        call(
            "ix_daily_report_intelligence_report_id",
            TABLE_NAME,
            ["report_id"],
        ),
        call(
            "ix_daily_report_intelligence_status_updated",
            TABLE_NAME,
            ["status", "updated_at"],
        ),
    ]


def test_downgrade_drops_indexes_then_table_in_order():
    migration = _load_migration()

    migration.downgrade()

    assert migration.op.method_calls == [
        call.drop_index(
            "ix_daily_report_intelligence_status_updated",
            table_name=TABLE_NAME,
        ),
        call.drop_index(
            "ix_daily_report_intelligence_report_id",
            table_name=TABLE_NAME,
        ),
        call.drop_table(TABLE_NAME),
    ]
