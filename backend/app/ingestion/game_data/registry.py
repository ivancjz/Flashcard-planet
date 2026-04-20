from __future__ import annotations

from backend.app.ingestion.game_data.base import GameDataClient
from backend.app.models.game import Game


class GameDataClientRegistry:
    """Singleton registry for game data clients."""

    _clients: dict[Game, GameDataClient] = {}

    @classmethod
    def register(cls, client: GameDataClient) -> None:
        cls._clients[client.game] = client

    @classmethod
    def get(cls, game: Game) -> GameDataClient:
        if game not in cls._clients:
            raise ValueError(
                f"No client registered for {game.value}. "
                f"Registered: {[g.value for g in cls._clients]}"
            )
        return cls._clients[game]

    @classmethod
    def all_live_games(cls) -> list[Game]:
        from backend.app.models.game import GAME_CONFIG
        return [g for g in cls._clients if GAME_CONFIG[g].status == "live"]

    @classmethod
    def clear(cls) -> None:
        """For tests only — do not call in production."""
        cls._clients.clear()
