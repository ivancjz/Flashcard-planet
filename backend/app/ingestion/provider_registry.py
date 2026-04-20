from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from backend.app.core.price_sources import (
    POKEMON_TCG_PRICE_SOURCE,
    ConfiguredPriceProvider,
    get_configured_price_providers,
)
from backend.app.ingestion.ebay_sold import EBAY_SOLD_PRICE_SOURCE, ingest_ebay_sold_cards
from backend.app.ingestion.pokemon_tcg import IngestionResult, ingest_game_cards


ProviderIngestor = Callable[..., IngestionResult]


@dataclass(frozen=True)
class ProviderIngestionBinding:
    slot: str
    source: str
    label: str
    is_primary: bool
    ingest_pool_cards: ProviderIngestor


def get_supported_provider_ingestors() -> dict[str, ProviderIngestor]:
    # Future provider_2 support only needs a new source constant plus an entry here.
    return {
        POKEMON_TCG_PRICE_SOURCE: ingest_game_cards,
        EBAY_SOLD_PRICE_SOURCE: ingest_ebay_sold_cards,
    }


def get_configured_provider_ingestors() -> list[ProviderIngestionBinding]:
    supported = get_supported_provider_ingestors()
    bindings: list[ProviderIngestionBinding] = []
    for provider in get_configured_price_providers():
        ingestor = supported.get(provider.source)
        if ingestor is None:
            continue
        bindings.append(
            ProviderIngestionBinding(
                slot=provider.slot,
                source=provider.source,
                label=provider.label,
                is_primary=provider.is_primary,
                ingest_pool_cards=ingestor,
            )
        )
    return bindings


def get_unimplemented_configured_providers() -> list[ConfiguredPriceProvider]:
    supported_sources = set(get_supported_provider_ingestors())
    return [
        provider
        for provider in get_configured_price_providers()
        if provider.source not in supported_sources
    ]
