"""
tests/conftest.py

Shared pytest fixtures for all tests.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

# Import all models so Base.metadata is fully populated before create_all
import backend.app.models  # noqa: F401

from backend.app.db.base import Base
from backend.app.models.game import Game


@pytest.fixture(scope="module")
def sqlite_engine():
    """SQLite in-memory engine with all schema tables created.

    Used by tests that need a real DB session but cannot connect to Postgres.
    All Postgres-specific dialect types (UUID, JSONB) fall back gracefully to
    VARCHAR/JSON on SQLite.
    """
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    # Emit PRAGMA foreign_keys=OFF so FK constraints don't block test setup
    # (we insert child rows without parent rows in some unit tests).
    @event.listens_for(eng, "connect")
    def _fk_pragma(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=OFF")

    Base.metadata.create_all(eng)
    return eng


@pytest.fixture
def sqlite_db(sqlite_engine):
    """Fresh Session per test; rolls back after each test for isolation."""
    with Session(sqlite_engine) as session:
        yield session
        session.rollback()


class MockGameDataClient:
    """Minimal GameDataClient-compatible mock for testing.

    Usage (TASK-009 YGO and beyond):
        from tests.conftest import MockGameDataClient
        client = MockGameDataClient(game=Game.YUGIOH)
        GameDataClientRegistry.register(client)

    Override fetch_card_by_external_id to return specific CardMetadata:
        client.card_responses["ygo-123"] = CardMetadata(...)
    """

    def __init__(self, game: Game = Game.POKEMON) -> None:
        self._game = game
        self.card_responses: dict = {}
        self.set_responses: list = []
        self.sets_list: list = []

    @property
    def game(self) -> Game:
        return self._game

    @property
    def rate_limit_per_second(self) -> float:
        return 100.0

    def fetch_card_by_external_id(self, external_id: str):
        return self.card_responses.get(external_id)

    def fetch_cards_by_set(self, set_code: str):
        return self.set_responses

    def list_sets(self):
        return self.sets_list

    def get_image_url(self, card, size: str = "normal"):
        images = (card.raw_payload or {}).get("images", {})
        key = "small" if size == "normal" else "large"
        return images.get(key)


@pytest.fixture
def mock_game_client():
    """Returns a MockGameDataClient for Game.POKEMON. Customize via attributes."""
    return MockGameDataClient(game=Game.POKEMON)
