from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# All Base Set Pokemon cards only.
# This intentionally covers base1-1 through base1-69 and excludes trainers and energy cards.
DEFAULT_POKEMON_TCG_CARD_IDS = ",".join(
    f"base1-{number}" for number in range(1, 70)
)
# Small activity-focused trial pool from Scarlet & Violet 151.
DEFAULT_POKEMON_TCG_TRIAL_CARD_IDS = ",".join(
    f"sv3pt5-{number}" for number in range(1, 26)
)
# High-activity trial pool from Prismatic Evolutions.
# This repo still ingests by explicit card id, so keep the pool definition transparent and
# schema-free instead of adding a broader catalog-query layer just for this experiment.
# Cards 148-180 are the premium top-end slice in sv8pt5, which skews toward chase cards,
# Special Illustration Rares, and Hyper Rares that are more likely to move than the broader set.
DEFAULT_POKEMON_TCG_HIGH_ACTIVITY_TRIAL_CARD_IDS = ",".join(
    f"sv8pt5-{number}" for number in range(148, 181)
)


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
    pokemon_tcg_card_ids: str = DEFAULT_POKEMON_TCG_CARD_IDS
    pokemon_tcg_trial_pool_label: str = "Scarlet & Violet 151 Trial"
    pokemon_tcg_trial_card_ids: str = DEFAULT_POKEMON_TCG_TRIAL_CARD_IDS
    pokemon_tcg_high_activity_pool_label: str = "High-Activity Trial"
    pokemon_tcg_high_activity_card_ids: str = DEFAULT_POKEMON_TCG_HIGH_ACTIVITY_TRIAL_CARD_IDS
    provider_1_source: str = "pokemon_tcg_api"
    provider_2_source: str = ""
    primary_price_source: str = "pokemon_tcg_api"
    pokemon_tcg_schedule_enabled: bool = True
    pokemon_tcg_schedule_seconds: int = 3600

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
