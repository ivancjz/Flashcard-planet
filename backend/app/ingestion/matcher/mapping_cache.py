from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.app.models.asset_mapping_cache import AssetMappingCache


def lookup_batch(db: Session, normalized_titles: list[str]) -> dict[str, AssetMappingCache]:
    if not normalized_titles:
        return {}
    rows = db.scalars(
        select(AssetMappingCache).where(AssetMappingCache.normalized_title.in_(normalized_titles))
    ).all()
    return {row.normalized_title: row for row in rows}


def write(db: Session, normalized_title: str, asset_id: UUID, confidence: Decimal, method: str) -> None:
    timestamp = datetime.now(UTC)
    stmt = insert(AssetMappingCache).values(
        normalized_title=normalized_title,
        asset_id=asset_id,
        confidence=confidence,
        match_method=method,
        last_hit_at=timestamp,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["normalized_title"],
        set_={
            "asset_id": asset_id,
            "confidence": confidence,
            "match_method": method,
            "last_hit_at": timestamp,
        },
    )
    db.execute(stmt)


def increment_hit(db: Session, cache_id: UUID) -> None:
    db.execute(
        update(AssetMappingCache)
        .where(AssetMappingCache.id == cache_id)
        .values(hit_count=AssetMappingCache.hit_count + 1, last_hit_at=datetime.now(UTC))
    )
