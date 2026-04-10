from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(slots=True)
class EbayListing:
    source_listing_id: str
    raw_title: str
    price_usd: Decimal
    sold_at: datetime
    currency_original: str
    url: str | None
