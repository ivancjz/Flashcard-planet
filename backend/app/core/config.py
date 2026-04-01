from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    project_name: str = "Flashcard Planet"
    environment: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = "/api/v1"
    database_url: str = Field(
        default="postgresql+psycopg://flashcard:flashcard@localhost:5432/flashcard_planet"
    )
    bot_token: str = ""
    discord_application_id: str = ""
    discord_guild_id: str = ""
    backend_base_url: str = "http://localhost:8000"
    scheduler_poll_seconds: int = 300
    pokemon_tcg_api_base_url: str = "https://api.pokemontcg.io/v2"
    pokemon_tcg_api_key: str = ""
    pokemon_tcg_card_ids: str = "base1-44,base1-58,base1-63"
    pokemon_tcg_schedule_enabled: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
