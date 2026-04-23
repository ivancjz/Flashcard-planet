from __future__ import annotations


def register_default_clients(api_key: str | None = None) -> None:
    """Register all default game data clients. Called once at app startup."""
    from backend.app.ingestion.game_data.pokemon_client import PokemonClient
    from backend.app.ingestion.game_data.registry import GameDataClientRegistry

    GameDataClientRegistry.register(PokemonClient(api_key=api_key))
    from backend.app.ingestion.game_data.yugioh_client import YugiohClient
    GameDataClientRegistry.register(YugiohClient())
