from __future__ import annotations

import importlib
import importlib.util
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


TABLE_NAME = "portfolio_lots"
EXPECTED_COLUMNS = [
    "id",
    "user_id",
    "asset_id",
    "quantity",
    "unit_cost_usd",
    "purchased_on",
    "created_at",
    "updated_at",
]
CHECK_CONDITIONS = {
    "ck_portfolio_lots_quantity_positive": "quantity > 0",
    "ck_portfolio_lots_unit_cost_non_negative": "unit_cost_usd >= 0",
}


def _load_model():
    module = importlib.import_module("backend.app.models.portfolio_lot")
    return module.PortfolioLot


def _load_migration():
    path = (
        Path(__file__).parent.parent
        / "migrations"
        / "versions"
        / "0044_add_portfolio_lots.py"
    )
    spec = importlib.util.spec_from_file_location("migration_0044", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    migration.op = MagicMock()
    return migration


def _compile(expression) -> str:
    return str(expression.compile(dialect=postgresql.dialect()))


def _upgrade_table_args(migration):
    migration.upgrade()
    migration.op.create_table.assert_called_once()
    return migration.op.create_table.call_args.args


def _assert_uuid(column: sa.Column) -> None:
    assert isinstance(column.type, UUID)
    assert column.type.as_uuid is True


def _assert_timestamptz(column: sa.Column) -> None:
    assert isinstance(column.type, sa.DateTime)
    assert column.type.timezone is True


def test_model_exports_exact_columns():
    model = _load_model()
    models_package = importlib.import_module("backend.app.models")

    assert model.__tablename__ == TABLE_NAME
    assert list(model.__table__.columns.keys()) == EXPECTED_COLUMNS
    assert models_package.PortfolioLot is model
    assert "PortfolioLot" in models_package.__all__


def test_model_defines_named_checks_and_only_required_indexes():
    model = _load_model()
    table = model.__table__

    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, sa.CheckConstraint)
    }
    assert checks == CHECK_CONDITIONS

    indexes = {index.name: index for index in table.indexes}
    assert set(indexes) == {
        "ix_portfolio_lots_user_asset",
        "ix_portfolio_lots_user_purchased_on",
    }
    assert [
        expression.name
        for expression in indexes["ix_portfolio_lots_user_asset"].expressions
    ] == ["user_id", "asset_id"]

    purchased_on_expressions = indexes[
        "ix_portfolio_lots_user_purchased_on"
    ].expressions
    assert purchased_on_expressions[0].name == "user_id"
    assert _compile(purchased_on_expressions[1]) == "purchased_on DESC"


def test_model_defines_foreign_keys_without_user_asset_uniqueness():
    model = _load_model()
    columns = model.__table__.c

    user_foreign_key = next(iter(columns.user_id.foreign_keys))
    assert user_foreign_key.target_fullname == "users.id"
    assert user_foreign_key.ondelete == "CASCADE"

    asset_foreign_key = next(iter(columns.asset_id.foreign_keys))
    assert asset_foreign_key.target_fullname == "assets.id"
    assert asset_foreign_key.ondelete is None

    unique_constraints = [
        constraint
        for constraint in model.__table__.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    ]
    assert unique_constraints == []


def test_model_defines_exact_types_defaults_and_nullability():
    model = _load_model()
    columns = model.__table__.c

    _assert_uuid(columns.id)
    assert isinstance(columns.id.default.arg(None), uuid.UUID)
    _assert_uuid(columns.user_id)
    _assert_uuid(columns.asset_id)
    assert isinstance(columns.quantity.type, sa.Integer)
    assert isinstance(columns.unit_cost_usd.type, sa.Numeric)
    assert columns.unit_cost_usd.type.precision == 12
    assert columns.unit_cost_usd.type.scale == 2
    assert isinstance(columns.purchased_on.type, sa.Date)
    _assert_timestamptz(columns.created_at)
    _assert_timestamptz(columns.updated_at)

    assert str(columns.created_at.server_default.arg) == "now()"
    assert columns.created_at.onupdate is None
    assert str(columns.updated_at.server_default.arg) == "now()"
    assert str(columns.updated_at.onupdate.arg) == "now()"
    assert all(not column.nullable for column in columns)


def test_model_defines_bidirectional_relationships_with_parent_delete_policies():
    model = _load_model()
    models_package = importlib.import_module("backend.app.models")

    asset_lots = models_package.Asset.portfolio_lots.property
    assert model.user.property.back_populates == "portfolio_lots"
    assert model.asset.property.back_populates == "portfolio_lots"
    assert models_package.User.portfolio_lots.property.back_populates == "user"
    assert asset_lots.back_populates == "asset"
    assert "delete-orphan" in models_package.User.portfolio_lots.property.cascade
    assert "delete" not in asset_lots.cascade
    assert "delete-orphan" not in asset_lots.cascade
    assert asset_lots.passive_deletes == "all"


def test_deleting_asset_does_not_delete_portfolio_lots():
    models_package = importlib.import_module("backend.app.models")
    from backend.app.db.base import Base

    original_jsonb_types = [
        (column, column.type)
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, JSONB)
    ]
    for column, _original_type in original_jsonb_types:
        column.type = sa.JSON()

    engine = sa.create_engine("sqlite:///:memory:")

    @sa.event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    statements: list[str] = []

    @sa.event.listens_for(engine, "before_cursor_execute")
    def _capture_sql(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ):
        statements.append(statement)

    try:
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            lot = models_package.PortfolioLot(
                user=models_package.User(email="portfolio-owner@example.com"),
                asset=models_package.Asset(
                    name="Protected portfolio asset",
                    external_id="protected-portfolio-asset",
                ),
                quantity=1,
                unit_cost_usd=Decimal("10.00"),
                purchased_on=date(2026, 7, 26),
            )
            session.add(lot)
            session.commit()
            lot_id = lot.id
            asset = lot.asset
            statements.clear()

            session.delete(asset)
            with pytest.raises(IntegrityError):
                session.commit()

            delete_statements = [
                statement.casefold()
                for statement in statements
                if statement.lstrip().upper().startswith("DELETE")
            ]
            assert any("assets" in statement for statement in delete_statements)
            assert all(
                "portfolio_lots" not in statement for statement in delete_statements
            )

            session.rollback()
            assert session.get(models_package.PortfolioLot, lot_id) is not None
    finally:
        engine.dispose()
        for column, original_type in original_jsonb_types:
            column.type = original_type


def test_migration_has_expected_revision_metadata():
    migration = _load_migration()

    assert migration.revision == "0044"
    assert migration.down_revision == "0043"
    assert migration.branch_labels is None
    assert migration.depends_on is None


def test_upgrade_creates_exact_columns_types_foreign_keys_and_checks():
    migration = _load_migration()

    table_args = _upgrade_table_args(migration)
    columns = {
        item.name: item for item in table_args[1:] if isinstance(item, sa.Column)
    }
    constraints = [
        item for item in table_args[1:] if isinstance(item, sa.Constraint)
    ]

    assert table_args[0] == TABLE_NAME
    assert list(columns) == EXPECTED_COLUMNS
    assert columns["id"].primary_key is True
    _assert_uuid(columns["id"])
    _assert_uuid(columns["user_id"])
    _assert_uuid(columns["asset_id"])
    assert isinstance(columns["quantity"].type, sa.Integer)
    assert isinstance(columns["unit_cost_usd"].type, sa.Numeric)
    assert columns["unit_cost_usd"].type.precision == 12
    assert columns["unit_cost_usd"].type.scale == 2
    assert isinstance(columns["purchased_on"].type, sa.Date)
    _assert_timestamptz(columns["created_at"])
    _assert_timestamptz(columns["updated_at"])
    assert str(columns["created_at"].server_default.arg) == "now()"
    assert str(columns["updated_at"].server_default.arg) == "now()"
    assert all(not column.nullable for column in columns.values())

    user_foreign_key = next(iter(columns["user_id"].foreign_keys))
    assert user_foreign_key.target_fullname == "users.id"
    assert user_foreign_key.ondelete == "CASCADE"
    asset_foreign_key = next(iter(columns["asset_id"].foreign_keys))
    assert asset_foreign_key.target_fullname == "assets.id"
    assert asset_foreign_key.ondelete is None

    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in constraints
        if isinstance(constraint, sa.CheckConstraint)
    }
    assert checks == CHECK_CONDITIONS
    assert not any(
        isinstance(constraint, sa.UniqueConstraint) for constraint in constraints
    )


def test_upgrade_creates_exact_required_indexes():
    migration = _load_migration()

    migration.upgrade()

    assert migration.op.create_index.call_count == 2
    assert migration.op.create_index.call_args_list[0] == call(
        "ix_portfolio_lots_user_asset",
        TABLE_NAME,
        ["user_id", "asset_id"],
    )

    purchased_on_call = migration.op.create_index.call_args_list[1]
    assert purchased_on_call.args[:2] == (
        "ix_portfolio_lots_user_purchased_on",
        TABLE_NAME,
    )
    assert purchased_on_call.args[2][0] == "user_id"
    assert _compile(purchased_on_call.args[2][1]) == "purchased_on DESC"
    assert purchased_on_call.kwargs == {}


def test_downgrade_drops_indexes_then_table_in_order():
    migration = _load_migration()

    migration.downgrade()

    assert migration.op.method_calls == [
        call.drop_index(
            "ix_portfolio_lots_user_purchased_on",
            table_name=TABLE_NAME,
        ),
        call.drop_index(
            "ix_portfolio_lots_user_asset",
            table_name=TABLE_NAME,
        ),
        call.drop_table(TABLE_NAME),
    ]
