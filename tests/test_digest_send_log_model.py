from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql, sqlite

from backend.app.models.digest_send_log import DigestSendLog


def test_digest_send_log_cards_included_compiles_for_sqlite_tests():
    ddl = str(CreateTable(DigestSendLog.__table__).compile(dialect=sqlite.dialect()))

    assert "cards_included" in ddl


def test_digest_send_log_cards_included_remains_postgresql_array():
    ddl = str(CreateTable(DigestSendLog.__table__).compile(dialect=postgresql.dialect()))

    assert "cards_included TEXT[]" in ddl
