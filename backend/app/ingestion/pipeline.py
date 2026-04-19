"""Ingestion pipeline orchestrator.

Runs a full batch: fetch → stage → cache check → rule engine → AI mapper → write assets + prices.
Every stage is idempotent — safe to re-run at any time.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.app.ingestion.ebay.client import EbayClient
from backend.app.ingestion.ebay.real_client import RealEbayClient
from backend.app.ingestion.ebay.stub_client import StubEbayClient
from backend.app.ingestion.matcher import ai_mapper, mapping_cache
from backend.app.ingestion.matcher.rule_engine import match_batch as rule_match_batch
from backend.app.ingestion.metrics import (
    INGESTION_AI_CALLS_TOTAL,
    INGESTION_AI_LISTINGS_MAPPED_TOTAL,
    INGESTION_ASSETS_WRITTEN_TOTAL,
    INGESTION_BATCH_DURATION_SECONDS,
    INGESTION_CACHE_HITS_TOTAL,
    INGESTION_ERRORS_TOTAL,
    INGESTION_HUMAN_REVIEW_QUEUE_TOTAL,
    INGESTION_LISTINGS_FETCHED_TOTAL,
    INGESTION_NOISE_FILTERED_TOTAL,
    INGESTION_LISTINGS_STAGED_TOTAL,
    INGESTION_RULE_MATCHES_TOTAL,
)
from backend.app.ingestion.staging import repository as staging_repo
from backend.app.models.asset import Asset
from backend.app.models.game import Game
from backend.app.models.human_review import HumanReviewQueue
from backend.app.models.price_history import PriceHistory
from backend.app.models.raw_listing import RawListing, RawListingStatus

logger = logging.getLogger(__name__)

AI_CONFIDENCE_AUTO = Decimal(os.getenv("AI_CONFIDENCE_THRESHOLD_AUTO", "0.75"))
AI_CONFIDENCE_REVIEW = Decimal(os.getenv("AI_CONFIDENCE_THRESHOLD_REVIEW", "0.50"))
BATCH_SIZE = int(os.getenv("INGESTION_BATCH_SIZE", "100"))
POKEMON_CATEGORY = "Pokemon"


def _log_json(level: int, event: str, **fields: object) -> None:
    logger.log(level, json.dumps({"event": event, **fields}, default=str, sort_keys=True))


@dataclass
class BatchResult:
    fetched: int = 0
    staged_new: int = 0
    cache_hits: int = 0
    rule_matched: int = 0
    ai_mapped: int = 0
    review_queued: int = 0
    assets_written: int = 0
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


def _get_client() -> EbayClient:
    stub_mode = os.getenv("EBAY_STUB_MODE", "true").lower() in {"true", "1", "yes"}
    if stub_mode:
        return StubEbayClient()
    return RealEbayClient()


def _confidence_bucket(confidence: Decimal) -> str:
    if confidence >= Decimal("0.90"):
        return "high"
    if confidence >= Decimal("0.75"):
        return "medium"
    if confidence >= Decimal("0.50"):
        return "low"
    return "review"


def _upsert_asset(db: Session, *, name: str, set_name: str | None, card_number: str | None,
                  language: str, variant: str | None, grade_company: str | None,
                  grade_score: Decimal | None, year: int | None, external_id: str | None) -> Asset:
    """Find existing asset or insert new one. Never creates duplicates."""
    # Try external_id first (fastest path)
    if external_id:
        existing = db.scalars(select(Asset).where(Asset.external_id == external_id)).first()
        if existing:
            return existing

    # Try canonical identity match
    stmt = select(Asset).where(
        Asset.name == name,
        Asset.set_name == set_name,
        Asset.card_number == card_number,
        Asset.language == (language or "EN"),
        Asset.variant == variant,
        Asset.grade_company == grade_company,
        Asset.grade_score == grade_score,
    )
    existing = db.scalars(stmt).first()
    if existing:
        return existing

    # Insert new asset
    asset = Asset(
        id=uuid.uuid4(),
        asset_class="TCG",
        category=POKEMON_CATEGORY,
        name=name,
        set_name=set_name,
        card_number=card_number,
        language=language or "EN",
        variant=variant,
        grade_company=grade_company,
        grade_score=grade_score,
        year=year,
        external_id=external_id,
    )
    db.add(asset)
    db.flush()  # get the id without committing
    return asset


def _write_price_event(db: Session, *, asset_id: uuid.UUID, price_usd: Decimal,
                       sold_at: datetime, source: str) -> None:
    """Insert price event. on_conflict_do_nothing for idempotency."""
    stmt = pg_insert(PriceHistory).values(
        id=uuid.uuid4(),
        asset_id=asset_id,
        price=price_usd,
        currency="USD",
        source=source,
        captured_at=sold_at,
    ).on_conflict_do_nothing()
    db.execute(stmt)


def _queue_human_review(db: Session, *, raw_listing: RawListing,
                        best_guess_asset_id: uuid.UUID | None,
                        best_guess_confidence: Decimal | None, reason: str) -> None:
    review = HumanReviewQueue(
        id=uuid.uuid4(),
        raw_listing_id=raw_listing.id,
        raw_title=raw_listing.raw_title,
        best_guess_asset_id=best_guess_asset_id,
        best_guess_confidence=best_guess_confidence,
        reason=reason,
    )
    db.add(review)


def _process_listing_with_rule_match(
    db: Session,
    raw_listing: RawListing,
    rule_result: object,
    result: BatchResult,
) -> bool:
    """Returns True if listing was fully processed by rule engine."""
    from backend.app.ingestion.matcher.rule_engine import RuleMatchResult
    assert isinstance(rule_result, RuleMatchResult)

    if not rule_result.matched:
        return False

    try:
        asset = _upsert_asset(
            db,
            name=rule_result.name or raw_listing.raw_title[:200],
            set_name=rule_result.set_name,
            card_number=rule_result.card_number,
            language=rule_result.language or "EN",
            variant=rule_result.variant,
            grade_company=rule_result.grade_company,
            grade_score=rule_result.grade_score,
            year=rule_result.year,
            external_id=rule_result.asset_external_id,
        )
        _write_price_event(
            db,
            asset_id=asset.id,
            price_usd=raw_listing.price_usd,
            sold_at=raw_listing.sold_at,
            source="ebay",
        )
        staging_repo.mark_processed(
            db, raw_listing.id, asset.id, rule_result.confidence, "rule"
        )
        mapping_cache.write(
            db,
            normalized_title=rule_result.normalized_title,
            asset_id=asset.id,
            confidence=rule_result.confidence,
            method="rule",
        )
        db.commit()
        INGESTION_RULE_MATCHES_TOTAL.labels(
            confidence_bucket=_confidence_bucket(rule_result.confidence)
        ).inc()
        INGESTION_ASSETS_WRITTEN_TOTAL.labels(method="rule").inc()
        result.rule_matched += 1
        result.assets_written += 1
        return True
    except Exception as exc:
        db.rollback()
        INGESTION_ERRORS_TOTAL.labels(stage="rule_write", error_type=type(exc).__name__).inc()
        result.errors.append(f"rule_write:{raw_listing.id}:{exc}")
        return False


def _process_listing_with_ai_result(
    db: Session,
    raw_listing: RawListing,
    ai_result: object,
    result: BatchResult,
) -> None:
    from backend.app.ingestion.matcher.ai_mapper import AiMatchResult
    assert isinstance(ai_result, AiMatchResult)

    if ai_result.confidence < AI_CONFIDENCE_REVIEW or ai_result.name is None:
        try:
            _queue_human_review(
                db,
                raw_listing=raw_listing,
                best_guess_asset_id=None,
                best_guess_confidence=ai_result.confidence,
                reason="ai_confidence_below_threshold",
            )
            db.execute(
                __import__("sqlalchemy", fromlist=["update"]).update(RawListing)
                .where(RawListing.id == raw_listing.id)
                .values(status=RawListingStatus.FAILED.value, error_reason="ai_low_confidence")
            )
            db.commit()
            INGESTION_HUMAN_REVIEW_QUEUE_TOTAL.inc()
            result.review_queued += 1
        except Exception as exc:
            db.rollback()
            INGESTION_ERRORS_TOTAL.labels(stage="review_queue", error_type=type(exc).__name__).inc()
            result.errors.append(f"review_queue:{raw_listing.id}:{exc}")
        return

    try:
        asset = _upsert_asset(
            db,
            name=ai_result.name,
            set_name=ai_result.set_name,
            card_number=ai_result.card_number,
            language=ai_result.language or "EN",
            variant=ai_result.variant,
            grade_company=ai_result.grade_company,
            grade_score=ai_result.grade_score,
            year=None,
            external_id=None,
        )
        _write_price_event(
            db,
            asset_id=asset.id,
            price_usd=raw_listing.price_usd,
            sold_at=raw_listing.sold_at,
            source="ebay",
        )
        staging_repo.mark_processed(
            db, raw_listing.id, asset.id, ai_result.confidence, "ai"
        )
        mapping_cache.write(
            db,
            normalized_title=ai_result.normalized_title,
            asset_id=asset.id,
            confidence=ai_result.confidence,
            method="ai",
        )
        db.commit()
        INGESTION_AI_LISTINGS_MAPPED_TOTAL.labels(
            confidence_bucket=_confidence_bucket(ai_result.confidence)
        ).inc()
        INGESTION_ASSETS_WRITTEN_TOTAL.labels(method="ai").inc()
        result.ai_mapped += 1
        result.assets_written += 1
    except Exception as exc:
        db.rollback()
        INGESTION_ERRORS_TOTAL.labels(stage="ai_write", error_type=type(exc).__name__).inc()
        result.errors.append(f"ai_write:{raw_listing.id}:{exc}")


async def run_batch(db: Session) -> BatchResult:
    """Execute one full ingestion batch. Idempotent — safe to re-run."""
    result = BatchResult()
    batch_start = time.monotonic()

    # ── Stage 1: Fetch ────────────────────────────────────────────────────────
    t = time.monotonic()
    client = _get_client()
    try:
        listings = await client.fetch_sold_listings(game=Game.POKEMON, limit=BATCH_SIZE)
    except Exception as exc:
        INGESTION_ERRORS_TOTAL.labels(stage="fetch", error_type=type(exc).__name__).inc()
        _log_json(logging.ERROR, "fetch_failed", error=str(exc))
        result.errors.append(f"fetch:{exc}")
        return result
    result.fetched = len(listings)
    INGESTION_LISTINGS_FETCHED_TOTAL.labels(source="ebay").inc(result.fetched)
    INGESTION_BATCH_DURATION_SECONDS.labels(stage="fetch").observe(time.monotonic() - t)

    # ── Stage 2: Stage (dedup) ────────────────────────────────────────────────
    t = time.monotonic()
    try:
        staged_new = staging_repo.upsert_batch(db, listings)
        result.staged_new = staged_new
        INGESTION_LISTINGS_STAGED_TOTAL.labels(source="ebay", deduped=str(result.fetched - staged_new)).inc(staged_new)
    except Exception as exc:
        INGESTION_ERRORS_TOTAL.labels(stage="stage", error_type=type(exc).__name__).inc()
        _log_json(logging.ERROR, "stage_failed", error=str(exc))
        result.errors.append(f"stage:{exc}")
        return result
    INGESTION_BATCH_DURATION_SECONDS.labels(stage="stage").observe(time.monotonic() - t)

    # ── Stage 3: Load pending rows ────────────────────────────────────────────
    t = time.monotonic()
    pending_rows = staging_repo.load_pending(db, limit=BATCH_SIZE)
    if not pending_rows:
        _log_json(logging.INFO, "batch_no_pending_rows")
        result.duration_ms = (time.monotonic() - batch_start) * 1000
        return result
    INGESTION_BATCH_DURATION_SECONDS.labels(stage="load_pending").observe(time.monotonic() - t)

    # ── Stage 3.5: AI noise filter ────────────────────────────────────────────
    t = time.monotonic()
    from backend.app.ingestion.noise_filter import filter_noise
    titles = [row.raw_title for row in pending_rows]
    is_real = filter_noise(titles)
    real_rows: list[RawListing] = []
    for row, real in zip(pending_rows, is_real):
        if real:
            real_rows.append(row)
        else:
            staging_repo.mark_processed(db, row.id, None, 0, "noise_filtered")
            db.commit()
            INGESTION_NOISE_FILTERED_TOTAL.inc()
            result.errors.append(f"noise_filtered:{row.id}")
    pending_rows = real_rows
    if not pending_rows:
        _log_json(logging.INFO, "batch_all_noise_filtered")
        result.duration_ms = (time.monotonic() - batch_start) * 1000
        return result
    INGESTION_BATCH_DURATION_SECONDS.labels(stage="noise_filter").observe(time.monotonic() - t)

    # ── Stage 4: Mapping cache lookup ─────────────────────────────────────────
    t = time.monotonic()
    from backend.app.ingestion.matcher.rule_engine import normalize_listing_title
    normalized_titles = [normalize_listing_title(row.raw_title) for row in pending_rows]
    cache_hits = mapping_cache.lookup_batch(db, normalized_titles)

    cache_hit_rows: list[RawListing] = []
    needs_matching: list[RawListing] = []
    for row, norm_title in zip(pending_rows, normalized_titles):
        if norm_title in cache_hits:
            cache_hit_rows.append(row)
        else:
            needs_matching.append(row)

    for row in cache_hit_rows:
        norm_title = normalize_listing_title(row.raw_title)
        cached = cache_hits[norm_title]
        try:
            _write_price_event(
                db,
                asset_id=cached.asset_id,
                price_usd=row.price_usd,
                sold_at=row.sold_at,
                source="ebay",
            )
            staging_repo.mark_processed(db, row.id, cached.asset_id, cached.confidence, "cache")
            mapping_cache.increment_hit(db, cached.id)
            db.commit()
            INGESTION_CACHE_HITS_TOTAL.inc()
            INGESTION_ASSETS_WRITTEN_TOTAL.labels(method="cache").inc()
            result.cache_hits += 1
            result.assets_written += 1
        except Exception as exc:
            db.rollback()
            INGESTION_ERRORS_TOTAL.labels(stage="cache_write", error_type=type(exc).__name__).inc()
            result.errors.append(f"cache_write:{row.id}:{exc}")
    INGESTION_BATCH_DURATION_SECONDS.labels(stage="cache_lookup").observe(time.monotonic() - t)

    if not needs_matching:
        result.duration_ms = (time.monotonic() - batch_start) * 1000
        _log_structured_summary(result)
        return result

    # ── Stage 5: Rule engine ──────────────────────────────────────────────────
    t = time.monotonic()
    rule_titles = [row.raw_title for row in needs_matching]
    rule_results = rule_match_batch(rule_titles)
    INGESTION_BATCH_DURATION_SECONDS.labels(stage="rule_engine").observe(time.monotonic() - t)

    needs_ai: list[tuple[RawListing, object]] = []
    for row, rule_result in zip(needs_matching, rule_results):
        matched = _process_listing_with_rule_match(db, row, rule_result, result)
        if not matched:
            needs_ai.append((row, rule_result))

    # ── Stage 6: AI mapper ────────────────────────────────────────────────────
    if needs_ai:
        t = time.monotonic()
        ai_titles = [row.raw_title for row, _ in needs_ai]
        INGESTION_AI_CALLS_TOTAL.inc()
        ai_results = ai_mapper.map_batch(ai_titles)
        INGESTION_BATCH_DURATION_SECONDS.labels(stage="ai_mapper").observe(time.monotonic() - t)

        for (row, _rule_result), ai_result in zip(needs_ai, ai_results):
            _process_listing_with_ai_result(db, row, ai_result, result)

    result.duration_ms = (time.monotonic() - batch_start) * 1000
    _log_structured_summary(result)
    return result


def _log_structured_summary(result: BatchResult) -> None:
    _log_json(
        logging.INFO,
        "batch_complete",
        fetched=result.fetched,
        staged_new=result.staged_new,
        cache_hits=result.cache_hits,
        rule_matched=result.rule_matched,
        ai_mapped=result.ai_mapped,
        review_queued=result.review_queued,
        assets_written=result.assets_written,
        errors=len(result.errors),
        duration_ms=round(result.duration_ms, 1),
    )
