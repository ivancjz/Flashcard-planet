from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest


CONSTRAINT_NAME = "ck_market_events_event_type"
EXPANDED_EVENT_TYPE_CONDITION = (
    "event_type IN ("
    "'INFLUENCER','SUPPLY','TOURNAMENT','RELEASE','REPRINT',"
    "'PRICE_CHANGE','ANNIVERSARY','COLLABORATION','LIMITED_PRODUCT',"
    "'POLICY','SOCIAL_TREND'"
    ")"
)
ORIGINAL_EVENT_TYPE_CONDITION = (
    "event_type IN ('INFLUENCER','SUPPLY','TOURNAMENT','RELEASE')"
)


def _load_migration():
    path = (
        Path(__file__).parent.parent
        / "migrations"
        / "versions"
        / "0042_add_catalyst_engine_fields.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0042", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    migration.op = MagicMock()
    return migration


def test_upgrade_replaces_event_type_constraint_with_all_canonical_types():
    migration = _load_migration()

    migration.upgrade()

    operations = migration.op.method_calls
    drop_constraint = call.drop_constraint(
        CONSTRAINT_NAME,
        "market_events",
        type_="check",
    )
    create_constraint = call.create_check_constraint(
        CONSTRAINT_NAME,
        "market_events",
        EXPANDED_EVENT_TYPE_CONDITION,
    )
    assert drop_constraint in operations
    assert create_constraint in operations
    assert operations.index(drop_constraint) < operations.index(create_constraint)


def test_downgrade_guards_data_before_restoring_original_constraint():
    migration = _load_migration()

    migration.downgrade()

    operations = migration.op.method_calls
    execute_operations = [
        (index, operation)
        for index, operation in enumerate(operations)
        if operation[0] == "execute"
    ]
    assert execute_operations, "downgrade must guard rows using expanded event types"
    assert len(execute_operations) == 1

    guard_index, guard_operation = execute_operations[0]
    assert guard_index == 0
    guard_sql = " ".join(guard_operation.args[0].split())
    assert "IF EXISTS" in guard_sql
    assert re.search(
        r"event_type NOT IN \(\s*"
        r"'INFLUENCER','SUPPLY','TOURNAMENT','RELEASE'\s*\)",
        guard_sql,
    )
    assert "RAISE EXCEPTION" in guard_sql
    assert "must be migrated or removed explicitly" in guard_sql

    drop_constraint = call.drop_constraint(
        CONSTRAINT_NAME,
        "market_events",
        type_="check",
    )
    create_constraint = call.create_check_constraint(
        CONSTRAINT_NAME,
        "market_events",
        ORIGINAL_EVENT_TYPE_CONDITION,
    )
    assert drop_constraint in operations
    assert create_constraint in operations
    assert operations.index(drop_constraint) < operations.index(create_constraint)


def test_downgrade_stops_when_event_type_guard_raises():
    migration = _load_migration()
    migration.op.execute.side_effect = RuntimeError("unsafe catalyst event types")

    with pytest.raises(RuntimeError, match="unsafe catalyst event types"):
        migration.downgrade()

    assert [operation[0] for operation in migration.op.method_calls] == ["execute"]
