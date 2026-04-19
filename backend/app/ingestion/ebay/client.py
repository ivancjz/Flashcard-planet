from __future__ import annotations

from typing import Protocol

from backend.app.ingestion.ebay.models import EbayListing
from backend.app.models.game import Game


class EbayClient(Protocol):
    async def fetch_sold_listings(self, game: Game, limit: int = 100) -> list[EbayListing]:
        ...
