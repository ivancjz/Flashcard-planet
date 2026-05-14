"""CardMarket daily price ingest for YGO assets.

Writes up to 3 price_history rows per asset per run:
  source='cardmarket_avg7'  -- 7-day avg of completed sales (primary signal)
  source='cardmarket_avg30' -- 30-day avg of completed sales (baseline)
  source='cardmarket_avg1'  -- 1-day avg (dispersion proxy; skipped when null)

All rows: currency='EUR', market_segment='raw'.
Cards without avg7 AND avg30 data are skipped.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ingestion.game_data.cardmarket_catalog import CardmarketCatalog, GAME_ID_YGO
from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory

logger = logging.getLogger(__name__)

CM_SOURCE_AVG1 = "cardmarket_avg1"
CM_SOURCE_AVG7 = "cardmarket_avg7"
CM_SOURCE_AVG30 = "cardmarket_avg30"


@dataclass
class CardmarketIngestionResult:
    assets_matched: int = 0
    assets_skipped_no_match: int = 0
    assets_skipped_no_price: int = 0
    price_points_written: int = 0
    captured_at: datetime | None = None
    skipped_not_modified: bool = False
    catalog_etag: str = ""


def ingest_cardmarket_ygo(
    session: Session,
    *,
    catalog: CardmarketCatalog | None = None,
    last_etag: str | None = None,
) -> CardmarketIngestionResult:
    """Match YGO assets to CardMarket products and write avg1/avg7/avg30 to price_history.

    If catalog is None, downloads fresh from S3.
    Pass last_etag (from scheduler_run_log.meta_json) to skip on 304.
    """
    if catalog is None:
        downloaded = CardmarketCatalog.download(game_id=GAME_ID_YGO, etag=last_etag)
        if downloaded is None:
            result = CardmarketIngestionResult()
            result.skipped_not_modified = True
            return result
        catalog = downloaded

    result = CardmarketIngestionResult()
    result.captured_at = datetime.now(UTC).replace(microsecond=0)

    ygo_assets = session.scalars(
        select(Asset).where(Asset.game == "yugioh")
    ).all()

    for asset in ygo_assets:
        cached_ids: list[int] = (asset.metadata_json or {}).get("cm_product_ids", [])
        if not cached_ids:
            cached_ids = catalog.product_ids_for_name(asset.name)
            if cached_ids:
                meta = dict(asset.metadata_json or {})
                meta["cm_product_ids"] = cached_ids
                asset.metadata_json = meta
                session.flush()

        if not cached_ids:
            result.assets_skipped_no_match += 1
            logger.debug("cardmarket_no_match asset=%s name=%r", asset.id, asset.name)
            continue

        matched = False
        # Multiple products can share the same card name (different printings across
        # sets/editions). All are written; the signal engine takes the most recent row
        # per source. When all printings share the same captured_at (daily ingest),
        # tie-breaking is non-deterministic — Phase 2 accepted behavior.
        # Disambiguation by expansion/rarity deferred to Phase 3; see CLAUDE.md §13.
        for pid in cached_ids:
            prices = catalog.prices_for_product(pid)
            avg7 = prices.get("avg7")
            avg30 = prices.get("avg30")
            avg1 = prices.get("avg1")

            if avg7 is None and avg30 is None:
                continue

            matched = True
            rows_to_write: list[tuple[str, float]] = []
            # Guard: skip zero and negative values — they produce wrong-direction deltas
            # downstream (e.g. avg30=0 with positive avg7 → spurious -100% signal).
            if avg7 is not None and avg7 > 0:
                rows_to_write.append((CM_SOURCE_AVG7, avg7))
            if avg30 is not None and avg30 > 0:
                rows_to_write.append((CM_SOURCE_AVG30, avg30))
            if avg1 is not None and avg1 > 0:
                rows_to_write.append((CM_SOURCE_AVG1, avg1))

            for source, price_val in rows_to_write:
                session.add(PriceHistory(
                    id=uuid.uuid4(),
                    asset_id=asset.id,
                    source=source,
                    currency="EUR",
                    price=Decimal(str(price_val)),
                    captured_at=result.captured_at,
                    market_segment="raw",
                ))
                result.price_points_written += 1

        if matched:
            result.assets_matched += 1
        else:
            result.assets_skipped_no_price += 1

    result.catalog_etag = catalog.etag
    logger.info(
        "cardmarket_ingest_complete matched=%s no_match=%s no_price=%s written=%s etag=%s",
        result.assets_matched, result.assets_skipped_no_match,
        result.assets_skipped_no_price, result.price_points_written, catalog.etag,
    )
    return result
