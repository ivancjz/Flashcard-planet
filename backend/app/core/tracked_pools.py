from __future__ import annotations

from dataclasses import dataclass

from backend.app.core.config import get_settings

PROVIDER_EXTERNAL_ID_PREFIX = "pokemontcg:"
BASE_SET_POOL_KEY = "base_set"
TRIAL_POOL_KEY = "trial_pool"
HIGH_ACTIVITY_TRIAL_POOL_KEY = "high_activity_trial_pool"
DEFAULT_BASE_SET_LABEL = "Base Set"
DEFAULT_TRIAL_POOL_LABEL = "Scarlet & Violet 151 Trial"
DEFAULT_HIGH_ACTIVITY_TRIAL_LABEL = "High-Activity Trial"


def parse_card_ids(raw_card_ids: str) -> list[str]:
    return [card_id.strip() for card_id in raw_card_ids.split(",") if card_id.strip()]


def derive_card_prefix(card_ids: list[str]) -> str:
    if not card_ids:
        raise ValueError("At least one card id is required to define a tracked pool.")

    prefixes = {card_id.split("-", 1)[0] for card_id in card_ids}
    if len(prefixes) != 1:
        raise ValueError(
            "Tracked pool card ids must share the same set prefix so they can be reported separately."
        )
    return prefixes.pop()


def build_external_id_like(card_prefix: str) -> str:
    return f"{PROVIDER_EXTERNAL_ID_PREFIX}{card_prefix}-%"


@dataclass(frozen=True)
class TrackedPokemonPool:
    key: str
    label: str
    card_ids: list[str]
    card_prefix: str

    @property
    def external_id_like(self) -> str:
        return build_external_id_like(self.card_prefix)


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
                card_prefix=derive_card_prefix(base_card_ids),
            )
        )

    trial_card_ids = parse_card_ids(settings.pokemon_tcg_trial_card_ids)
    if trial_card_ids:
        pools.append(
            TrackedPokemonPool(
                key=TRIAL_POOL_KEY,
                label=(settings.pokemon_tcg_trial_pool_label.strip() or DEFAULT_TRIAL_POOL_LABEL),
                card_ids=trial_card_ids,
                card_prefix=derive_card_prefix(trial_card_ids),
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
                card_prefix=derive_card_prefix(high_activity_card_ids),
            )
        )

    return pools
