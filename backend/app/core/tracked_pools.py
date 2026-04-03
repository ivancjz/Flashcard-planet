from __future__ import annotations

from dataclasses import dataclass

from backend.app.core.config import get_settings

PROVIDER_EXTERNAL_ID_PREFIX = "pokemontcg:"
BASE_SET_POOL_KEY = "base_set"
TRIAL_POOL_KEY = "trial_pool"
HIGH_ACTIVITY_TRIAL_POOL_KEY = "high_activity_trial_pool"
HIGH_ACTIVITY_V2_POOL_KEY = "high_activity_v2_pool"
PRIMARY_SMART_OBSERVATION_POOL_KEY = HIGH_ACTIVITY_V2_POOL_KEY
DEFAULT_BASE_SET_LABEL = "Base Set"
DEFAULT_TRIAL_POOL_LABEL = "Scarlet & Violet 151 Trial"
DEFAULT_HIGH_ACTIVITY_TRIAL_LABEL = "High-Activity Trial"
DEFAULT_HIGH_ACTIVITY_V2_LABEL = "High-Activity v2"


def parse_card_ids(raw_card_ids: str) -> list[str]:
    return [card_id.strip() for card_id in raw_card_ids.split(",") if card_id.strip()]


def build_external_id_pattern(card_id: str) -> str:
    return f"{PROVIDER_EXTERNAL_ID_PREFIX}{card_id}:%"


@dataclass(frozen=True)
class TrackedPokemonPool:
    key: str
    label: str
    card_ids: list[str]

    @property
    def external_id_patterns(self) -> tuple[str, ...]:
        return tuple(build_external_id_pattern(card_id) for card_id in self.card_ids)


def get_tracked_pokemon_pools() -> list[TrackedPokemonPool]:
    settings = get_settings()
    pools: list[TrackedPokemonPool] = []

    base_card_ids = parse_card_ids(settings.pokemon_tcg_card_ids)
    if base_card_ids:
        pools.append(
            TrackedPokemonPool(
                key=BASE_SET_POOL_KEY,
                label=DEFAULT_BASE_SET_LABEL,
                card_ids=base_card_ids,
            )
        )

    trial_card_ids = parse_card_ids(settings.pokemon_tcg_trial_card_ids)
    if trial_card_ids:
        pools.append(
            TrackedPokemonPool(
                key=TRIAL_POOL_KEY,
                label=(settings.pokemon_tcg_trial_pool_label.strip() or DEFAULT_TRIAL_POOL_LABEL),
                card_ids=trial_card_ids,
            )
        )

    high_activity_card_ids = parse_card_ids(settings.pokemon_tcg_high_activity_card_ids)
    if high_activity_card_ids:
        pools.append(
            TrackedPokemonPool(
                key=HIGH_ACTIVITY_TRIAL_POOL_KEY,
                label=(
                    settings.pokemon_tcg_high_activity_pool_label.strip()
                    or DEFAULT_HIGH_ACTIVITY_TRIAL_LABEL
                ),
                card_ids=high_activity_card_ids,
            )
        )

    high_activity_v2_card_ids = parse_card_ids(settings.pokemon_tcg_high_activity_v2_card_ids)
    if high_activity_v2_card_ids:
        pools.append(
            TrackedPokemonPool(
                key=HIGH_ACTIVITY_V2_POOL_KEY,
                label=(
                    settings.pokemon_tcg_high_activity_v2_pool_label.strip()
                    or DEFAULT_HIGH_ACTIVITY_V2_LABEL
                ),
                card_ids=high_activity_v2_card_ids,
            )
        )

    return pools


def get_primary_smart_observation_pool() -> TrackedPokemonPool | None:
    return next(
        (
            pool
            for pool in get_tracked_pokemon_pools()
            if pool.key == PRIMARY_SMART_OBSERVATION_POOL_KEY
        ),
        None,
    )
