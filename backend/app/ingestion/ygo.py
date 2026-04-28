"""Yu-Gi-Oh ingestion: fetch per-set-entry assets from YGOPRODeck and write to price_history."""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.app.ingestion.game_data.yugioh_client import YugiohClient
from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory

logger = logging.getLogger(__name__)

YGO_PRICE_SOURCE = "ygoprodeck_api"

YGO_PHASE2_SETS = [
    # Original 5
    "LEDE",   # Legacy of Destruction (2024)
    "PHNI",   # Phantom Nightmare (2024)
    "AGOV",   # Age of Overlord (2023)
    "POTE",   # Power of the Elements (2022)
    "TOCH",   # Toon Chaos (2020) — high-value staples
    # Expanded 8
    "MZMI",   # Maze of Millennia (2024)
    "INFO",   # Infinite Forbidden (2024)
    "DUNE",   # Duelist Nexus (2023)
    "RA01",   # Rarity Collection Quarter Century Edition (2024)
    "RA02",   # Rarity Collection 2 (2025)
    "BLTR",   # Battles of Legend: Terminal Revenge (2024)
    "CYAC",   # Cyberstorm Access (2023)
    "WISU",   # Wild Survivors (2023)
]


@dataclass
class YgoIngestionResult:
    set_codes: list[str] = field(default_factory=list)
    assets_created: int = 0
    assets_seen: int = 0
    price_points_inserted: int = 0
    entries_skipped_no_price: int = 0
    sets_failed: list[str] = field(default_factory=list)
    captured_at: datetime | None = None


def _upsert_ygo_asset(
    session: Session,
    *,
    external_id: str,
    name: str,
    set_name: str,
    set_code: str,
    rarity: str,
    card_type: str | None,
    image_url: str | None,
    metadata: dict,
) -> tuple[Asset, bool]:
    """Return (asset, created). created=True if a new row was inserted."""
    existing = session.scalars(select(Asset).where(Asset.external_id == external_id)).first()
    if existing:
        return existing, False

    asset = Asset(
        id=uuid.uuid4(),
        asset_class="TCG",
        game="yugioh",
        category=card_type or "Yu-Gi-Oh",
        name=name,
        set_name=set_name,
        card_number=set_code,
        language="EN",
        variant=rarity,
        external_id=external_id,
        metadata_json=metadata,
    )
    session.add(asset)
    session.flush()
    return asset, True


def ingest_ygo_sets(
    session: Session,
    set_codes: list[str] | None = None,
) -> YgoIngestionResult:
    """Fetch YGO set entries from YGOPRODeck and upsert assets + price_history.

    One asset per (konami_id, set_entry_code, rarity) combination.
    Entries with set_price == "0" are skipped — no market data.
    """
    codes = set_codes or YGO_PHASE2_SETS
    result = YgoIngestionResult(set_codes=codes)
    captured_at = datetime.now(UTC).replace(microsecond=0)
    result.captured_at = captured_at

    client = YugiohClient()
    rate_delay = 1.0 / client.rate_limit_per_second

    for set_code in codes:
        try:
            entries = client.fetch_set_entries(set_code)
        except Exception:
            logger.exception("ygo_ingest_set_failed set_code=%s", set_code)
            result.sets_failed.append(set_code)
            continue

        logger.info("ygo_ingest_set_fetched set_code=%s entries=%s", set_code, len(entries))

        for raw, entry in entries:
            result.assets_seen += 1
            konami_id = raw["id"]
            set_entry_code = entry["set_code"]
            rarity = entry["set_rarity"]
            price_str = entry.get("set_price", "0") or "0"

            try:
                price = Decimal(price_str)
            except InvalidOperation:
                result.entries_skipped_no_price += 1
                continue

            if price <= 0:
                result.entries_skipped_no_price += 1
                continue

            external_id = YugiohClient.make_external_id(konami_id, set_entry_code, rarity)
            card_images = raw.get("card_images") or []
            image_url = card_images[0].get("image_url_small") if card_images else None

            asset, created = _upsert_ygo_asset(
                session,
                external_id=external_id,
                name=raw["name"],
                set_name=entry["set_name"],
                set_code=set_entry_code,
                rarity=rarity,
                card_type=raw.get("type"),
                image_url=image_url,
                metadata={
                    "konami_id": konami_id,
                    "set_code": set_entry_code,
                    "set_name": entry["set_name"],
                    "rarity": rarity,
                    "image_url": image_url,
                    "images": {"small": image_url},
                    "atk": raw.get("atk"),
                    "def": raw.get("def"),
                    "level": raw.get("level"),
                    "race": raw.get("race"),
                    "attribute": raw.get("attribute"),
                },
            )

            if created:
                result.assets_created += 1

            stmt = pg_insert(PriceHistory).values(
                id=uuid.uuid4(),
                asset_id=asset.id,
                source=YGO_PRICE_SOURCE,
                currency="USD",
                price=price,
                captured_at=captured_at,
                market_segment='raw',
            ).on_conflict_do_nothing()
            rows = session.execute(stmt)
            if rows.rowcount:
                result.price_points_inserted += 1

            time.sleep(rate_delay)

        session.commit()
        logger.info(
            "ygo_ingest_set_done set_code=%s assets_seen=%s price_points=%s",
            set_code, result.assets_seen, result.price_points_inserted,
        )

    logger.info(
        "ygo_ingest_complete sets=%s assets_created=%s price_points=%s sets_failed=%s",
        len(codes), result.assets_created, result.price_points_inserted, result.sets_failed,
    )
    return result
