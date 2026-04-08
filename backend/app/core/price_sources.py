from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.price_history import PriceHistory

SAMPLE_PRICE_SOURCE = "sample_seed"
POKEMON_TCG_PRICE_SOURCE = "pokemon_tcg_api"
EBAY_SOLD_PRICE_SOURCE = "ebay_sold"
PROVIDER_1_SLOT = "provider_1"
PROVIDER_2_SLOT = "provider_2"

PRICE_SOURCE_LABELS = {
    POKEMON_TCG_PRICE_SOURCE: "Pokemon TCG API",
    EBAY_SOLD_PRICE_SOURCE: "eBay Sold Listings",
}


@dataclass(frozen=True)
class ConfiguredPriceProvider:
    slot: str
    source: str
    label: str
    is_primary: bool


def get_price_source_label(source: str) -> str:
    if not source:
        return "<unconfigured>"
    return PRICE_SOURCE_LABELS.get(source, source.replace("_", " ").title())


def _get_configured_provider_slot_pairs() -> list[tuple[str, str]]:
    settings = get_settings()
    return [
        (PROVIDER_1_SLOT, settings.provider_1_source.strip()),
        (PROVIDER_2_SLOT, settings.provider_2_source.strip()),
    ]


def get_primary_price_source() -> str:
    configured_source = get_settings().primary_price_source.strip()
    if configured_source:
        return configured_source

    for _slot, source in _get_configured_provider_slot_pairs():
        if source:
            return source
    return POKEMON_TCG_PRICE_SOURCE


def get_configured_price_providers() -> list[ConfiguredPriceProvider]:
    primary_source = get_primary_price_source()
    providers: list[ConfiguredPriceProvider] = []
    for slot, source in _get_configured_provider_slot_pairs():
        if not source:
            continue
        providers.append(
            ConfiguredPriceProvider(
                slot=slot,
                source=source,
                label=get_price_source_label(source),
                is_primary=(source == primary_source),
            )
        )
    return providers


def get_active_price_source_filter(db: Session):
    # User-facing reads stay scoped to one active source at a time so future providers
    # can be added beside it without merging their histories into a single stream.
    primary_source = get_primary_price_source()
    has_primary_rows = (
        db.scalar(
            select(PriceHistory.id)
            .where(PriceHistory.source == primary_source)
            .limit(1)
        )
        is not None
    )
    if has_primary_rows:
        return PriceHistory.source == primary_source
    return PriceHistory.source == SAMPLE_PRICE_SOURCE
