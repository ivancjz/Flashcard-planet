from __future__ import annotations

from contextlib import contextmanager

from .config import Config

config = Config("alembic.ini")


def is_offline_mode() -> bool:
    return False


def configure(**_kwargs) -> None:
    return None


@contextmanager
def begin_transaction():
    yield


def run_migrations() -> None:
    return None
