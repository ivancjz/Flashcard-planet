import os
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
# High-activity trial pool from Prismatic Evolutions — RETIRED.
# The 33-card contiguous sv8pt5-148..180 slice has been replaced by the tighter
# High-Activity v2 pool below, which targets only the 13 highest-relevance cards.
# Keeping the default empty so the scheduler stops ingesting these cards.
# Operators who still want to observe the full 33-card slice can restore the list
# in their local .env: POKEMON_TCG_HIGH_ACTIVITY_CARD_IDS=sv8pt5-148,...,sv8pt5-180
DEFAULT_POKEMON_TCG_HIGH_ACTIVITY_TRIAL_CARD_IDS = ""
# High-activity v2 diagnostic pool from Prismatic Evolutions.
# This tighter list keeps the experiment inside the existing explicit-card-id model while
# focusing on the most market-relevant single raw cards currently tracked in sv8pt5.
DEFAULT_POKEMON_TCG_HIGH_ACTIVITY_V2_CARD_IDS = ",".join(
    (
        "sv8pt5-149",
        "sv8pt5-150",
        "sv8pt5-153",
        "sv8pt5-155",
        "sv8pt5-156",
        "sv8pt5-157",
        "sv8pt5-161",
        "sv8pt5-162",
        "sv8pt5-165",
        "sv8pt5-166",
        "sv8pt5-167",
        "sv8pt5-168",
        "sv8pt5-179",
    )
)


class Settings(BaseSettings):
    project_name: str = "Flashcard Planet"
    environment: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = int(os.environ.get("PORT", 8000))
    api_prefix: str = "/api/v1"
    database_url: str = Field(
        default="postgresql+psycopg://flashcard:flashcard@localhost:5432/flashcard_planet"
    )
    bot_token: str = ""
    discord_application_id: str = ""
    discord_guild_id: str = ""
    backend_base_url: str = f"http://localhost:{os.environ.get('PORT', 8000)}"
    scheduler_poll_seconds: int = 300
    pokemon_tcg_api_base_url: str = "https://api.pokemontcg.io/v2"
    pokemon_tcg_api_key: str = ""
    pokemon_tcg_card_ids: str = DEFAULT_POKEMON_TCG_CARD_IDS
    pokemon_tcg_bulk_set_ids: str = "me3,me2pt5,me2,me1,sv10,rsv10pt5,zsv10pt5,sv9,sv8pt5,sv8,sv3pt5,base1,base2,base3"
    pokemon_tcg_trial_pool_label: str = "Scarlet & Violet 151 Trial"
    pokemon_tcg_trial_card_ids: str = DEFAULT_POKEMON_TCG_TRIAL_CARD_IDS
    pokemon_tcg_high_activity_pool_label: str = "High-Activity Trial"
    pokemon_tcg_high_activity_card_ids: str = DEFAULT_POKEMON_TCG_HIGH_ACTIVITY_TRIAL_CARD_IDS
    pokemon_tcg_high_activity_v2_pool_label: str = "High-Activity v2"
    pokemon_tcg_high_activity_v2_card_ids: str = DEFAULT_POKEMON_TCG_HIGH_ACTIVITY_V2_CARD_IDS
    ebay_app_id: str = ""
    ebay_cert_id: str = ""
    ebay_sold_lookback_hours: int = Field(default=24, ge=1, le=168)
    ebay_search_keywords: str = ""  # comma-separated search terms
    ebay_scheduled_ingest_enabled: bool = False
    ebay_ingest_cron: str = "0 3 * * *"  # UTC; default 03:00 daily
    ebay_daily_budget_limit: int = Field(default=500, ge=1, le=5000)
    ebay_max_calls_per_run: int = Field(default=150, ge=1, le=5000)
    provider_1_source: str = "pokemon_tcg_api"
    provider_2_source: str = ""
    primary_price_source: str = "pokemon_tcg_api"
    admin_api_key: str = ""
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    xai_api_key: str = ""
    xai_model: str = "grok-4.20-reasoning"
    xai_base_url: str = "https://api.x.ai/v1"
    llm_provider: str = "anthropic"
    secret_key: str = Field(default="change-me-in-production-use-a-long-random-string")
    discord_client_id: str = ""
    discord_client_secret: str = ""
    discord_redirect_uri: str = ""   # e.g. https://yourdomain.com/auth/callback
    jwt_expire_days: int = Field(default=30, ge=1)
    signal_sweep_interval_seconds: int = Field(default=900, ge=60)
    ingest_schedule_enabled: bool = True
    ingest_interval_hours: float = Field(default=24.0, gt=0)
    gap_history_threshold: int = Field(default=7, ge=1)
    gap_set_coverage_threshold: float = Field(default=0.5, gt=0, le=1)
    pokemon_tcg_schedule_enabled: bool = True
    pokemon_tcg_schedule_seconds: int = 3600

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def resolved_ingest_schedule_enabled(self) -> bool:
        if "ingest_schedule_enabled" in self.model_fields_set:
            return self.ingest_schedule_enabled
        if "pokemon_tcg_schedule_enabled" in self.model_fields_set:
            return self.pokemon_tcg_schedule_enabled
        return self.ingest_schedule_enabled

    @property
    def resolved_ingest_interval_hours(self) -> float:
        if "ingest_interval_hours" in self.model_fields_set:
            return self.ingest_interval_hours
        if "pokemon_tcg_schedule_seconds" in self.model_fields_set:
            return max(self.pokemon_tcg_schedule_seconds / 3600, 1 / 3600)
        return self.ingest_interval_hours

    @property
    def resolved_ingest_interval_seconds(self) -> int:
        return max(int(round(self.resolved_ingest_interval_hours * 3600)), 1)

    @property
    def bulk_set_id_list(self) -> list[str]:
        return [s.strip() for s in self.pokemon_tcg_bulk_set_ids.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
