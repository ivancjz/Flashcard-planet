from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.backstage.routes import require_admin_key
from backend.app.ingestion.matcher import mapping_cache
from backend.app.ingestion.matcher.rule_engine import normalize_listing_title
from backend.app.models.asset import Asset
from backend.app.models.human_review import HumanReviewQueue
from backend.app.models.price_history import PriceHistory
from backend.app.models.raw_listing import RawListing, RawListingStatus

router = APIRouter(prefix="/admin/review", tags=["admin-review"])

REVIEWABLE_FAILED_REASONS = {"ai_low_confidence"}
REVIEWABLE_LISTING_STATUSES = {
    RawListingStatus.PENDING.value,
    RawListingStatus.PENDING_AI.value,
}


class ReviewItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    raw_title: str
    best_guess_asset_id: uuid.UUID | None
    best_guess_asset_name: str | None
    best_guess_confidence: Decimal | None
    reason: str | None
    created_at: datetime


class ReviewListResponse(BaseModel):
    items: list[ReviewItem]
    total_pending: int
    limit: int
    offset: int


class AssetResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    set_name: str | None
    variant: str | None


class OverrideRequest(BaseModel):
    asset_id: uuid.UUID


def _now() -> datetime:
    return datetime.now(UTC)


def _load_unresolved_review(db: Session, review_id: uuid.UUID) -> HumanReviewQueue:
    review = db.get(HumanReviewQueue, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review item not found.")
    if review.resolved_at is not None:
        raise HTTPException(status_code=409, detail="Review item already resolved.")
    return review


def _load_reviewable_listing(db: Session, raw_listing_id: uuid.UUID) -> RawListing:
    listing = db.get(RawListing, raw_listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Linked raw listing not found.")
    if listing.status in REVIEWABLE_LISTING_STATUSES:
        return listing
    if (
        listing.status == RawListingStatus.FAILED.value
        and listing.error_reason in REVIEWABLE_FAILED_REASONS
    ):
        return listing
    raise HTTPException(
        status_code=409,
        detail="Listing already processed by another workflow.",
    )


def _stamp_resolved(review: HumanReviewQueue, resolution_type: str) -> None:
    review.resolved_at = _now()
    review.resolved_by = "operator"
    review.resolution_type = resolution_type


def _write_price_event(db: Session, asset_id: uuid.UUID, listing: RawListing) -> None:
    db.add(
        PriceHistory(
            asset_id=asset_id,
            source="ebay",
            currency="USD",
            price=listing.price_usd,
            captured_at=listing.sold_at,
        )
    )


def _mark_listing_processed(
    db: Session,
    listing: RawListing,
    asset_id: uuid.UUID,
    confidence: Decimal,
    method: str,
) -> None:
    db.execute(
        update(RawListing)
        .where(RawListing.id == listing.id)
        .values(
            status=RawListingStatus.PROCESSED.value,
            mapped_asset_id=asset_id,
            confidence=confidence,
            match_method=method,
            processed_at=_now(),
            error_reason=None,
        )
    )


def _mark_listing_dismissed(db: Session, listing: RawListing) -> None:
    db.execute(
        update(RawListing)
        .where(RawListing.id == listing.id)
        .values(
            status=RawListingStatus.FAILED.value,
            mapped_asset_id=None,
            confidence=None,
            match_method="human_review_dismiss",
            processed_at=_now(),
            error_reason="review_dismissed",
        )
    )


@router.get("", response_model=ReviewListResponse)
def list_review_items(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> ReviewListResponse:
    total_pending = int(
        db.scalar(
            select(func.count())
            .select_from(HumanReviewQueue)
            .where(HumanReviewQueue.resolved_at.is_(None))
        )
        or 0
    )

    rows = list(
        db.scalars(
            select(HumanReviewQueue)
            .where(HumanReviewQueue.resolved_at.is_(None))
            .order_by(HumanReviewQueue.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )

    asset_ids = sorted({row.best_guess_asset_id for row in rows if row.best_guess_asset_id})
    asset_names: dict[uuid.UUID, str] = {}
    if asset_ids:
        assets = db.scalars(select(Asset).where(Asset.id.in_(asset_ids))).all()
        asset_names = {asset.id: asset.name for asset in assets}

    items = [
        ReviewItem(
            id=row.id,
            raw_title=row.raw_title,
            best_guess_asset_id=row.best_guess_asset_id,
            best_guess_asset_name=asset_names.get(row.best_guess_asset_id)
            if row.best_guess_asset_id
            else None,
            best_guess_confidence=row.best_guess_confidence,
            reason=row.reason,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return ReviewListResponse(
        items=items,
        total_pending=total_pending,
        limit=limit,
        offset=offset,
    )


@router.get("/assets/search", response_model=list[AssetResult])
def search_assets(
    q: str = Query(..., min_length=3),
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> list[AssetResult]:
    pattern = f"%{q.strip()}%"
    rows = db.scalars(
        select(Asset)
        .where(
            or_(
                Asset.name.ilike(pattern),
                Asset.set_name.ilike(pattern),
                Asset.card_number.ilike(pattern),
                Asset.variant.ilike(pattern),
            )
        )
        .order_by(Asset.name.asc(), Asset.set_name.asc())
        .limit(20)
    ).all()
    return [
        AssetResult(id=row.id, name=row.name, set_name=row.set_name, variant=row.variant)
        for row in rows
    ]


@router.post("/{review_id}/accept")
def accept_review(
    review_id: uuid.UUID,
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> dict[str, str]:
    try:
        review = _load_unresolved_review(db, review_id)
        if review.best_guess_asset_id is None:
            raise HTTPException(status_code=422, detail="No best guess to accept.")
        asset = db.get(Asset, review.best_guess_asset_id)
        if asset is None:
            raise HTTPException(status_code=422, detail="Best-guess asset not found.")
        listing = _load_reviewable_listing(db, review.raw_listing_id)
        confidence = review.best_guess_confidence or Decimal("1.000")
        _write_price_event(db, asset.id, listing)
        _mark_listing_processed(db, listing, asset.id, confidence, "human_review_accept")
        mapping_cache.write(
            db,
            normalized_title=normalize_listing_title(listing.raw_title),
            asset_id=asset.id,
            confidence=confidence,
            method="human_review",
        )
        _stamp_resolved(review, "accepted")
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return {"status": "accepted", "review_id": str(review_id)}


@router.post("/{review_id}/override")
def override_review(
    review_id: uuid.UUID,
    payload: OverrideRequest,
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> dict[str, str]:
    try:
        review = _load_unresolved_review(db, review_id)
        asset = db.get(Asset, payload.asset_id)
        if asset is None:
            raise HTTPException(status_code=422, detail="Asset not found.")
        listing = _load_reviewable_listing(db, review.raw_listing_id)
        confidence = Decimal("1.000")
        _write_price_event(db, asset.id, listing)
        _mark_listing_processed(db, listing, asset.id, confidence, "human_review_override")
        mapping_cache.write(
            db,
            normalized_title=normalize_listing_title(listing.raw_title),
            asset_id=asset.id,
            confidence=confidence,
            method="human_review",
        )
        _stamp_resolved(review, "overridden")
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return {
        "status": "overridden",
        "review_id": str(review_id),
        "asset_id": str(payload.asset_id),
    }


@router.post("/{review_id}/dismiss")
def dismiss_review(
    review_id: uuid.UUID,
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> dict[str, str]:
    try:
        review = _load_unresolved_review(db, review_id)
        listing = _load_reviewable_listing(db, review.raw_listing_id)
        _mark_listing_dismissed(db, listing)
        _stamp_resolved(review, "dismissed")
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    return {"status": "dismissed", "review_id": str(review_id)}
