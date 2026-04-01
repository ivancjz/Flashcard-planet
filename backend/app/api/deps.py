from collections.abc import Generator

from sqlalchemy.orm import Session

from backend.app.db.session import get_db


def get_database() -> Generator[Session, None, None]:
    yield from get_db()
