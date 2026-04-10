from __future__ import annotations

from typing import Protocol

from backend.app.ingestion.ebay.models import EbayListing


class EbayClient(Protocol):
    async def fetch_sold_listings(self, category: str, limit: int = 100) -> list[EbayListing]:
        ...
