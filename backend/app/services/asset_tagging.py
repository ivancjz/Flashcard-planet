from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from backend.app.core.tracked_pools import HIGH_ACTIVITY_TRIAL_POOL_KEY, get_tracked_pokemon_pools
from backend.app.models.asset import Asset

MODERN_RELEASE_YEAR_THRESHOLD = 2020
UNKNOWN_RARITY_LABEL = "Unknown Rarity"
UNKNOWN_LANGUAGE_LABEL = "Unknown Language"
UNKNOWN_ERA_LABEL = "Unknown Era"
MODERN_ERA_LABEL = f"Modern ({MODERN_RELEASE_YEAR_THRESHOLD}+)"
OLDER_ERA_LABEL = f"Older (<{MODERN_RELEASE_YEAR_THRESHOLD})"
CHASE_TAG_LABEL = "Chase / Collectible"
STANDARD_TAG_LABEL = "Standard"
HIGH_ACTIVITY_TAG_LABEL = "High-Activity Candidate"
STANDARD_ACTIVITY_TAG_LABEL = "Standard Activity"

RARITY_BUCKET_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Illustration / Special Art Rare",
        (
            "special illustration rare",
            "illustration rare",
            "special art rare",
            "art rare",
        ),
    ),
    (
        "Ultra / Secret Rare",
        (
            "hyper rare",
            "secret rare",
            "ultra rare",
            "double rare",
            "ace spec",
            "shiny rare",
            "radiant rare",
            "amazing rare",
        ),
    ),
    (
        "Holo / Classic Rare",
        (
            "rare holo",
            "holo rare",
            "classic collection",
        ),
    ),
    ("Rare", ("rare",)),
    ("Uncommon", ("uncommon",)),
    ("Common", ("common",)),
)
COLLECTIBLE_VARIANT_KEYWORDS = ("holofoil", "1st edition")
COLLECTIBLE_RARITY_BUCKETS = frozenset(
    {
        "Illustration / Special Art Rare",
        "Ultra / Secret Rare",
    }
)
TAG_DIMENSION_ORDER = (
    "rarity",
    "language",
    "collectible_chase",
    "era",
    "high_activity_candidate",
)
TAG_DIMENSION_LABELS = {
    "rarity": "Rarity",
    "language": "Language",
    "collectible_chase": "Collectible / Chase",
    "era": "Era",
    "high_activity_candidate": "High-Activity Candidate",
}
TAG_VALUE_SORT_ORDERS = {
    "rarity": {
        "Illustration / Special Art Rare": 0,
        "Ultra / Secret Rare": 1,
        "Holo / Classic Rare": 2,
        "Rare": 3,
        "Uncommon": 4,
        "Common": 5,
        UNKNOWN_RARITY_LABEL: 99,
    },
    "language": {
        "English": 0,
        "Japanese": 1,
        "Other": 2,
        UNKNOWN_LANGUAGE_LABEL: 99,
    },
    "collectible_chase": {
        CHASE_TAG_LABEL: 0,
        STANDARD_TAG_LABEL: 1,
    },
    "era": {
        MODERN_ERA_LABEL: 0,
        OLDER_ERA_LABEL: 1,
        UNKNOWN_ERA_LABEL: 99,
    },
    "high_activity_candidate": {
        HIGH_ACTIVITY_TAG_LABEL: 0,
        STANDARD_ACTIVITY_TAG_LABEL: 1,
    },
}


@dataclass(frozen=True)
class AssetTagProfile:
    rarity: str
    language: str
    collectible_chase: bool
    era: str
    high_activity_candidate: bool


def _clean_string(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _metadata(asset: Asset) -> dict:
    return asset.metadata_json or {}


def _normalize_language(raw_language: str | None) -> str:
    if raw_language is None:
        return UNKNOWN_LANGUAGE_LABEL

    normalized = raw_language.strip().upper()
    if normalized in {"EN", "ENGLISH"}:
        return "English"
    if normalized in {"JP", "JA", "JPN", "JAPANESE"}:
        return "Japanese"
    if len(normalized) <= 3:
        return "Other"
    return normalized.title()


def _normalize_rarity(raw_rarity: str | None) -> str:
    if raw_rarity is None:
        return UNKNOWN_RARITY_LABEL

    normalized = raw_rarity.strip()
    if not normalized:
        return UNKNOWN_RARITY_LABEL

    lowered = normalized.lower()
    for label, keywords in RARITY_BUCKET_RULES:
        if any(keyword in lowered for keyword in keywords):
            return label
    return normalized.title()


def _derive_era(release_year: int | None) -> str:
    if release_year is None:
        return UNKNOWN_ERA_LABEL
    if release_year >= MODERN_RELEASE_YEAR_THRESHOLD:
        return MODERN_ERA_LABEL
    return OLDER_ERA_LABEL


def _extract_provider_card_id(asset: Asset) -> str | None:
    metadata = _metadata(asset)
    provider_card_id = _clean_string(metadata.get("provider_card_id"))
    if provider_card_id is not None:
        return provider_card_id

    external_id = _clean_string(asset.external_id)
    if external_id and external_id.startswith("pokemontcg:"):
        parts = external_id.split(":")
        if len(parts) >= 3:
            return parts[1]
    return None


@lru_cache
def _high_activity_trial_card_ids() -> frozenset[str]:
    for pool in get_tracked_pokemon_pools():
        if pool.key == HIGH_ACTIVITY_TRIAL_POOL_KEY:
            return frozenset(pool.card_ids)
    return frozenset()


def classify_asset_tags(asset: Asset) -> AssetTagProfile:
    metadata = _metadata(asset)
    rarity = _normalize_rarity(_clean_string(metadata.get("rarity")))
    language = _normalize_language(_clean_string(asset.language) or _clean_string(metadata.get("language")))
    era = _derive_era(asset.year)
    variant_lower = (_clean_string(asset.variant) or "").lower()
    collectible_chase = rarity in COLLECTIBLE_RARITY_BUCKETS or (
        era == OLDER_ERA_LABEL and any(keyword in variant_lower for keyword in COLLECTIBLE_VARIANT_KEYWORDS)
    )
    provider_card_id = _extract_provider_card_id(asset)
    in_high_activity_trial = (
        provider_card_id in _high_activity_trial_card_ids()
        if provider_card_id is not None
        else False
    )
    high_activity_candidate = in_high_activity_trial or (
        collectible_chase and era == MODERN_ERA_LABEL
    )
    return AssetTagProfile(
        rarity=rarity,
        language=language,
        collectible_chase=collectible_chase,
        era=era,
        high_activity_candidate=high_activity_candidate,
    )


def get_asset_tag_values(asset: Asset) -> dict[str, str]:
    profile = classify_asset_tags(asset)
    return {
        "rarity": profile.rarity,
        "language": profile.language,
        "collectible_chase": CHASE_TAG_LABEL if profile.collectible_chase else STANDARD_TAG_LABEL,
        "era": profile.era,
        "high_activity_candidate": (
            HIGH_ACTIVITY_TAG_LABEL
            if profile.high_activity_candidate
            else STANDARD_ACTIVITY_TAG_LABEL
        ),
    }


def get_tag_value_sort_key(dimension: str, value: str) -> tuple[int, str]:
    order = TAG_VALUE_SORT_ORDERS.get(dimension, {})
    return (order.get(value, 50), value)
