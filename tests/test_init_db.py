from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


def _connect_ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.__enter__.return_value = MagicMock(name="connection")
    ctx.__exit__.return_value = False
    return ctx


def _set_version(ctx: MagicMock, version: str | None) -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = version
    ctx.__enter__.return_value.exec_driver_sql.return_value = result


def _set_columns(
    mock_inspect: MagicMock,
    *,
    missing: dict[str, set[str]] | None = None,
) -> None:
    import backend.app.models  # noqa: F401
    from backend.app.db.base import Base

    missing = missing or {}

    def _get_columns(table_name: str) -> list[dict[str, str]]:
        table = Base.metadata.tables.get(table_name)
        if table is None:
            return []
        names = [column.name for column in table.columns if column.name not in missing.get(table_name, set())]
        return [{"name": name} for name in names]

    mock_inspect.return_value.get_columns.side_effect = _get_columns


def test_init_db_stamps_head_for_full_create_all_schema_without_alembic_version() -> None:
    from backend.app.db.init_db import _expected_model_tables

    expected_tables = _expected_model_tables()

    with (
        patch("backend.app.db.init_db.engine") as mock_engine,
        patch("backend.app.db.init_db.inspect") as mock_inspect,
        patch("backend.app.db.init_db.command.stamp") as mock_stamp,
        patch("backend.app.db.init_db.command.upgrade") as mock_upgrade,
    ):
        ctx = _connect_ctx()
        _set_version(ctx, None)
        mock_engine.connect.return_value = ctx
        mock_inspect.return_value.get_table_names.return_value = sorted(expected_tables)
        _set_columns(mock_inspect)

        from backend.app.db.init_db import init_db

        init_db()

    mock_stamp.assert_called_once()
    stamp_args = mock_stamp.call_args[0]
    assert stamp_args[1] == "head"
    mock_upgrade.assert_called_once()
    upgrade_args = mock_upgrade.call_args[0]
    assert upgrade_args[1] == "head"


def test_init_db_stamps_0001_for_partial_pre_alembic_schema() -> None:
    with (
        patch("backend.app.db.init_db.engine") as mock_engine,
        patch("backend.app.db.init_db.inspect") as mock_inspect,
        patch("backend.app.db.init_db.command.stamp") as mock_stamp,
        patch("backend.app.db.init_db.command.upgrade") as mock_upgrade,
    ):
        ctx = _connect_ctx()
        _set_version(ctx, None)
        mock_engine.connect.return_value = ctx
        mock_inspect.return_value.get_table_names.return_value = ["assets", "price_history"]
        _set_columns(mock_inspect)

        from backend.app.db.init_db import init_db

        init_db()

    mock_stamp.assert_called_once()
    stamp_args = mock_stamp.call_args[0]
    assert stamp_args[1] == "0001"
    mock_upgrade.assert_called_once()


def test_init_db_restamps_head_when_full_schema_is_wrongly_marked_0001() -> None:
    from backend.app.db.init_db import _expected_model_tables

    expected_tables = _expected_model_tables()
    tables_with_version = sorted(expected_tables | {"alembic_version"})

    with (
        patch("backend.app.db.init_db.engine") as mock_engine,
        patch("backend.app.db.init_db.inspect") as mock_inspect,
        patch("backend.app.db.init_db.command.stamp") as mock_stamp,
        patch("backend.app.db.init_db.command.upgrade") as mock_upgrade,
    ):
        ctx = _connect_ctx()
        _set_version(ctx, "0001")
        mock_engine.connect.return_value = ctx
        mock_inspect.return_value.get_table_names.return_value = tables_with_version
        _set_columns(mock_inspect)

        from backend.app.db.init_db import init_db

        init_db()

    mock_stamp.assert_called_once()
    stamp_args = mock_stamp.call_args[0]
    assert stamp_args[1] == "head"
    mock_upgrade.assert_called_once()


def test_init_db_does_not_restamp_head_when_head_only_table_columns_are_missing() -> None:
    from backend.app.db.init_db import _expected_model_tables

    expected_tables = _expected_model_tables()
    tables_with_version = sorted(expected_tables | {"alembic_version"})

    with (
        patch("backend.app.db.init_db.engine") as mock_engine,
        patch("backend.app.db.init_db.inspect") as mock_inspect,
        patch("backend.app.db.init_db.command.stamp") as mock_stamp,
        patch("backend.app.db.init_db.command.upgrade") as mock_upgrade,
    ):
        ctx = _connect_ctx()
        _set_version(ctx, "0001")
        mock_engine.connect.return_value = ctx
        mock_inspect.return_value.get_table_names.return_value = tables_with_version
        _set_columns(mock_inspect, missing={"human_review_queue": {"resolution_type"}})

        from backend.app.db.init_db import init_db

        init_db()

    mock_stamp.assert_not_called()
    mock_upgrade.assert_called_once()


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    suite = unittest.TestSuite()
    for test in (
        test_init_db_stamps_head_for_full_create_all_schema_without_alembic_version,
        test_init_db_stamps_0001_for_partial_pre_alembic_schema,
        test_init_db_restamps_head_when_full_schema_is_wrongly_marked_0001,
        test_init_db_does_not_restamp_head_when_head_only_table_columns_are_missing,
    ):
        suite.addTest(unittest.FunctionTestCase(test))
    return suite
