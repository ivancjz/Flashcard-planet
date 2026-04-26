from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.price_sources import POKEMON_TCG_PRICE_SOURCE, SAMPLE_PRICE_SOURCE
from backend.app.models.price_history import PriceHistory
from backend.app.ingestion.rule_engine_patches import preflight_observation
from backend.app.services.observation_match_service import stage_observation_match

logger = logging.getLogger(__name__)

PRICE_TYPE_PRIORITY = (
    "normal",
    "holofoil",
    "reverseHolofoil",
    "1stEditionHolofoil",
    "1stEditionNormal",
    "unlimitedHolofoil",
    "unlimitedNormal",
)
PRICE_VALUE_PRIORITY = ("market", "mid", "low")
RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
MAX_FETCH_ATTEMPTS = 3


class ProviderUnavailableError(RuntimeError):
    """Raised when the upstream Pokemon TCG API is unavailable after retries."""


@dataclass
class PricePointInsertResult:
    inserted: bool
    previous_price: Decimal | None = None
    price_changed: bool | None = None


@dataclass
class IngestionResult:
    cards_requested: int = 0
    cards_processed: int = 0
    cards_failed: int = 0
    cards_skipped_no_price: int = 0
    assets_created: int = 0
    assets_updated: int = 0
    price_points_inserted: int = 0
    price_points_changed: int = 0
    price_points_unchanged: int = 0
    price_points_skipped_existing_timestamp: int = 0
    sample_rows_deleted: int = 0
    observations_logged: int = 0
    observations_matched: int = 0
    observations_unmatched: int = 0
    observations_require_review: int = 0
    observation_match_status_counts: dict[str, int] = field(default_factory=dict)
    inserted_asset_names: list[str] = field(default_factory=list)
    latest_captured_at: datetime | None = None
    api_calls_used: int = 0


@dataclass
class BackfillResult:
    missing_price: int = 0
    missing_image: int = 0
    attempted: int = 0
    price_filled: int = 0
    image_filled: int = 0
    skipped_no_price: int = 0
    errors: int = 0


def parse_card_ids(raw_card_ids: str) -> list[str]:
    return [card_id.strip() for card_id in raw_card_ids.split(",") if card_id.strip()]


def build_headers() -> dict[str, str]:
    settings = get_settings()
    headers = {"Accept": "application/json"}
    if settings.pokemon_tcg_api_key:
        headers["X-Api-Key"] = settings.pokemon_tcg_api_key
    return headers


def normalize_variant(price_type: str) -> str:
    return price_type.replace("Holofoil", " Holofoil").replace("Edition", " Edition").title()


def parse_release_year(card: dict[str, Any]) -> int | None:
    release_date = card.get("set", {}).get("releaseDate")
    if not release_date:
        return None

    for date_format in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(release_date, date_format).year
        except ValueError:
            continue

    logger.warning(
        "Could not parse Pokemon TCG release date %r for card %s.",
        release_date,
        card.get("id"),
    )
    return None


def choose_price_snapshot(card: dict[str, Any]) -> tuple[str, str, Decimal] | None:
    tcgplayer = card.get("tcgplayer") or {}
    prices = tcgplayer.get("prices") or {}

    for price_type in PRICE_TYPE_PRIORITY:
        bucket = prices.get(price_type)
        if not bucket:
            continue

        for field_name in PRICE_VALUE_PRIORITY:
            value = bucket.get(field_name)
            if value is None:
                continue
            return "tcgplayer", field_name, Decimal(str(value))

    try:
        cardmarket = card.get("cardmarket") or {}
        cardmarket_prices = cardmarket.get("prices") or {}
    except AttributeError:
        cardmarket = getattr(card, "cardmarket", None)
        cardmarket_prices = getattr(cardmarket, "prices", None)
        if cardmarket_prices is None:
            return None

    for field_name in ("trendPrice", "avg30", "lowPriceExPlus"):
        try:
            value = cardmarket_prices.get(field_name)
        except AttributeError:
            value = getattr(cardmarket_prices, field_name, None)
        if value in (None, 0, 0.0):
            continue
        return "cardmarket", field_name, Decimal(str(value))

    return None


def _extract_tcg_language(card: dict[str, Any]) -> str:
    """Derive asset language from TCG API card data.

    Standard API cards are English. Non-English sets use distinct set ID prefixes.
    Returns a two-letter lowercase code, defaulting to 'en'.
    """
    set_id: str = (card.get("set") or {}).get("id", "")
    JP_PREFIXES = ("jp", "JPN", "sv1j", "sv2j", "sv3j")
    KR_PREFIXES = ("ko",)
    if any(set_id.startswith(p) for p in JP_PREFIXES):
        return "jp"
    if any(set_id.startswith(p) for p in KR_PREFIXES):
        return "kr"
    lang = card.get("language") or card.get("lang")
    if lang:
        return str(lang).lower()[:2]
    return "en"


def _extract_tcg_variant(card: dict[str, Any]) -> str | None:
    """Derive asset variant from TCG API card data using subtypes and rarity.

    Returns a canonical variant string (matching CardVariant values where
    possible) or None for base/standard prints.
    """
    subtypes: list[str] = card.get("subtypes") or []
    rarity: str = (card.get("rarity") or "").lower()
    name: str = card.get("name", "")
    subtype_lower = [s.lower() for s in subtypes]

    if "1st edition" in subtype_lower:
        return "first_edition"
    if "shadowless" in subtype_lower or "shadowless" in name.lower():
        return "shadowless"
    if "secret" in rarity or "rainbow" in rarity or "hyper" in rarity:
        return "secret_rare"
    if "full art" in rarity or "alternate art" in rarity:
        return "full_art"
    if "promo" in rarity or "promo" in subtype_lower:
        return "promo"
    if any("reverse" in s for s in subtype_lower):
        return "reverse_holo"
    if "holo" in rarity:
        return "holo"
    return None


def build_asset_payload(card: dict[str, Any], price_source: str, price_field: str) -> dict[str, Any]:
    card_id = card["id"]
    return {
        "asset_class": "TCG",
        "game": "pokemon",
        "name": card["name"],
        "set_name": card.get("set", {}).get("name"),
        "card_number": card.get("number"),
        "year": parse_release_year(card),
        "language": _extract_tcg_language(card),
        "variant": _extract_tcg_variant(card),
        "grade_company": None,
        "grade_score": None,
        "external_id": card_id,
        "metadata_json": {
            "provider": POKEMON_TCG_PRICE_SOURCE,
            "provider_card_id": card_id,
            "provider_price_type": price_source,
            "provider_price_field": price_field,
            "rarity": card.get("rarity"),
            "set_id": card.get("set", {}).get("id"),
            "set_series": card.get("set", {}).get("series"),
            "set_release_date": card.get("set", {}).get("releaseDate"),
            "set": {
                "id": card.get("set", {}).get("id"),
                "name": card.get("set", {}).get("name"),
                "total": card.get("set", {}).get("total"),
                "printedTotal": card.get("set", {}).get("printedTotal"),
            },
            "images": card.get("images") or {},
            "tcgplayer_url": card.get("tcgplayer", {}).get("url"),
        },
        "notes": "Imported from Pokemon TCG API.",
    }


def extract_raw_language(card: dict[str, Any]) -> str:
    raw_language = card.get("language") or card.get("lang")
    if raw_language is None:
        return "EN"
    return str(raw_language).strip() or "EN"


def add_price_point(
    session: Session,
    asset_id,
    source: str,
    currency: str,
    price: Decimal,
    captured_at: datetime,
    market_segment: str,
) -> PricePointInsertResult:
    already_exists = session.scalar(
        select(PriceHistory).where(
            PriceHistory.asset_id == asset_id,
            PriceHistory.source == source,
            PriceHistory.captured_at == captured_at,
        )
    )
    if already_exists:
        return PricePointInsertResult(inserted=False)

    previous_row = session.execute(
        select(PriceHistory.price)
        .where(
            PriceHistory.asset_id == asset_id,
            PriceHistory.source == source,
        )
        .order_by(PriceHistory.captured_at.desc())
        .limit(1)
    ).first()
    previous_price = Decimal(previous_row.price) if previous_row is not None else None

    session.add(
        PriceHistory(
            asset_id=asset_id,
            source=source,
            currency=currency,
            price=price,
            captured_at=captured_at,
            market_segment=market_segment,
        )
    )
    return PricePointInsertResult(
        inserted=True,
        previous_price=previous_price,
        price_changed=(previous_price != price) if previous_price is not None else None,
    )


def _record_observation_result(
    result: IngestionResult,
    *,
    match_status: str,
    matched: bool,
    requires_review: bool,
) -> None:
    result.observations_logged += 1
    if matched:
        result.observations_matched += 1
    else:
        result.observations_unmatched += 1
    if requires_review:
        result.observations_require_review += 1
    result.observation_match_status_counts[match_status] = (
        result.observation_match_status_counts.get(match_status, 0) + 1
    )


def _parse_retry_after(response: httpx.Response) -> float | None:
    """Parse Retry-After header. Returns seconds as float, or None if absent/invalid.

    Accepts both the delta-seconds form ("120") and the HTTP-date form
    ("Wed, 22 Apr 2026 15:30:00 GMT") as specified in RFC 9110 §10.2.3.
    """
    retry_after = response.headers.get("Retry-After")
    if retry_after is None:
        return None
    try:
        return float(retry_after)
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(retry_after)
        return max((target - datetime.now(UTC)).total_seconds(), 0.0)
    except Exception:
        return None


def _compute_retry_delay(response: httpx.Response | None, attempt: int) -> float:
    """Prefer Retry-After header if present, otherwise exponential backoff."""
    if response is not None:
        retry_after = _parse_retry_after(response)
        if retry_after is not None:
            return min(retry_after, 60.0)
    fallback = [2.0, 5.0, 15.0]
    return fallback[min(attempt - 1, len(fallback) - 1)]


def fetch_card(client: httpx.Client, card_id: str) -> dict[str, Any]:
    settings = get_settings()
    last_exception: Exception | None = None
    url = f"{settings.pokemon_tcg_api_base_url.rstrip('/')}/cards/{card_id}"

    for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
        try:
            response = client.get(url)
            if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_FETCH_ATTEMPTS:
                delay_seconds = _compute_retry_delay(response, attempt)
                logger.warning(
                    "Retrying Pokemon TCG card %s after HTTP %s on attempt %s/%s (sleeping %.1fs).",
                    card_id, response.status_code, attempt, MAX_FETCH_ATTEMPTS, delay_seconds,
                )
                time.sleep(delay_seconds)
                continue
            response.raise_for_status()
            payload = response.json()
            return payload["data"]
        except httpx.HTTPStatusError as exc:
            last_exception = exc
            status_code = exc.response.status_code
            if status_code in RETRYABLE_STATUS_CODES and attempt < MAX_FETCH_ATTEMPTS:
                delay_seconds = _compute_retry_delay(exc.response, attempt)
                logger.warning(
                    "Retrying Pokemon TCG card %s after HTTP %s on attempt %s/%s (sleeping %.1fs).",
                    card_id, status_code, attempt, MAX_FETCH_ATTEMPTS, delay_seconds,
                )
                time.sleep(delay_seconds)
                continue
            if status_code in RETRYABLE_STATUS_CODES:
                raise ProviderUnavailableError(
                    f"Pokemon TCG API returned HTTP {status_code} for card {card_id} after retries."
                ) from exc
            raise
        except (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError) as exc:
            last_exception = exc
            if attempt < MAX_FETCH_ATTEMPTS:
                delay_seconds = _compute_retry_delay(None, attempt)
                logger.warning(
                    "Retrying Pokemon TCG card %s after network error on attempt %s/%s: %s",
                    card_id, attempt, MAX_FETCH_ATTEMPTS, exc,
                )
                time.sleep(delay_seconds)
                continue
            raise ProviderUnavailableError(
                f"Pokemon TCG API is unreachable for card {card_id} after retries."
            ) from exc

    raise RuntimeError(f"Failed to fetch card {card_id}") from last_exception


def ingest_game_cards(
    session: Session,
    card_ids: list[str] | None = None,
    *,
    game: "Game" = None,
    clear_sample_seed: bool = True,
) -> IngestionResult:
    from backend.app.models.game import Game as _Game
    from backend.app.ingestion.game_data.registry import GameDataClientRegistry
    if game is None:
        game = _Game.POKEMON
    try:
        data_client = GameDataClientRegistry.get(game)
    except ValueError:
        if game != _Game.POKEMON:
            raise
        from backend.app.ingestion.game_data.pokemon_client import PokemonClient
        data_client = PokemonClient()

    settings = get_settings()
    configured_card_ids = card_ids or parse_card_ids(settings.pokemon_tcg_card_ids)
    if not configured_card_ids:
        raise ValueError("No card IDs configured for ingestion.")

    result = IngestionResult(cards_requested=len(configured_card_ids))

    if clear_sample_seed:
        delete_result = session.execute(delete(PriceHistory).where(PriceHistory.source == SAMPLE_PRICE_SOURCE))
        result.sample_rows_deleted = int(delete_result.rowcount or 0)

    ingested_at = datetime.now(UTC).replace(microsecond=0)
    result.latest_captured_at = ingested_at

    failed_provider_unavailable: list[str] = []

    for card_id in configured_card_ids:
        try:
            metadata = data_client.fetch_card_by_external_id(card_id)
            if metadata is None:
                result.cards_failed += 1
                logger.warning("Card %s not found (404), skipping.", card_id)
                continue
            card = metadata.raw_payload
            chosen_price = choose_price_snapshot(card)
            if chosen_price is None:
                _card_name = card.get("name", "")
                _pf = preflight_observation(_card_name)
                _normalised_name = _pf.normalised_title if not _pf.should_skip else _card_name
                observation_result = stage_observation_match(
                    session,
                    provider=POKEMON_TCG_PRICE_SOURCE,
                    external_item_id=card["id"],
                    raw_title=_normalised_name,
                    raw_set_name=card.get("set", {}).get("name"),
                    raw_card_number=card.get("number"),
                    raw_language=extract_raw_language(card),
                    asset_payload=None,
                    unmatched_reason="No usable tcgplayer price snapshot was returned for this provider observation.",
                )
                _record_observation_result(
                    result,
                    match_status=observation_result.observation_log.match_status,
                    matched=observation_result.can_write_price_history,
                    requires_review=observation_result.observation_log.requires_review,
                )
                logger.warning("Skipping card %s because no usable tcgplayer price was returned.", card_id)
                result.cards_skipped_no_price += 1
                continue

            price_source, price_field, price = chosen_price
            asset_payload = build_asset_payload(card, price_source, price_field)
            _card_name = card.get("name", "")
            _pf = preflight_observation(_card_name)
            _normalised_name = _pf.normalised_title if not _pf.should_skip else _card_name
            observation_result = stage_observation_match(
                session,
                provider=POKEMON_TCG_PRICE_SOURCE,
                external_item_id=card["id"],
                raw_title=_normalised_name,
                raw_set_name=card.get("set", {}).get("name"),
                raw_card_number=card.get("number"),
                raw_language=extract_raw_language(card),
                asset_payload=asset_payload,
            )
            _record_observation_result(
                result,
                match_status=observation_result.observation_log.match_status,
                matched=observation_result.can_write_price_history,
                requires_review=observation_result.observation_log.requires_review,
            )
            if not observation_result.can_write_price_history or observation_result.matched_asset is None:
                logger.warning(
                    "Skipping card %s because the observation could not be matched canonically: %s",
                    card_id,
                    observation_result.observation_log.reason,
                )
                continue

            asset = observation_result.matched_asset
            if observation_result.asset_created:
                result.assets_created += 1
            else:
                result.assets_updated += 1

            insert_result = add_price_point(
                session,
                asset.id,
                source=POKEMON_TCG_PRICE_SOURCE,
                currency="USD",
                price=price,
                captured_at=ingested_at,
                market_segment='raw',
            )
            if insert_result.inserted:
                result.price_points_inserted += 1
                if insert_result.price_changed is True:
                    result.price_points_changed += 1
                elif insert_result.price_changed is False:
                    result.price_points_unchanged += 1
                if asset.name not in result.inserted_asset_names:
                    result.inserted_asset_names.append(asset.name)
            else:
                result.price_points_skipped_existing_timestamp += 1

            result.cards_processed += 1
        except ProviderUnavailableError as exc:
            result.cards_failed += 1
            failed_provider_unavailable.append(card_id)
            logger.warning(
                "Provider unavailable for card %s: %s. Skipping and continuing.",
                card_id,
                exc,
            )
            continue
        except Exception:
            result.cards_failed += 1
            logger.exception("Failed to ingest card %s. Continuing with the remaining cards.", card_id)
        finally:
            time.sleep(1.0 / data_client.rate_limit_per_second)

    if failed_provider_unavailable:
        logger.error(
            "Pokemon TCG provider unavailable for %s card(s): %s",
            len(failed_provider_unavailable),
            ", ".join(failed_provider_unavailable),
        )

    session.commit()
    logger.info(
        "Ingest summary: cards_requested=%s cards_processed=%s cards_failed=%s cards_skipped_no_price=%s assets_created=%s assets_updated=%s price_points_inserted=%s price_points_changed=%s price_points_unchanged=%s price_points_skipped_existing_timestamp=%s sample_rows_deleted=%s observations_logged=%s observations_matched=%s observations_unmatched=%s observations_require_review=%s observation_match_status_counts=%s inserted_assets=%s latest_captured_at=%s",
        result.cards_requested,
        result.cards_processed,
        result.cards_failed,
        result.cards_skipped_no_price,
        result.assets_created,
        result.assets_updated,
        result.price_points_inserted,
        result.price_points_changed,
        result.price_points_unchanged,
        result.price_points_skipped_existing_timestamp,
        result.sample_rows_deleted,
        result.observations_logged,
        result.observations_matched,
        result.observations_unmatched,
        result.observations_require_review,
        result.observation_match_status_counts,
        ", ".join(result.inserted_asset_names) if result.inserted_asset_names else "<none>",
        result.latest_captured_at.isoformat() if result.latest_captured_at else "<none>",
    )
    return result


def _query_missing_price(session: Session, *, limit: int, primary_source: str) -> list[str]:
    """Return provider_card_id values for assets that have no PriceHistory row
    for primary_source. Only assets whose metadata_json contains a provider_card_id
    are included (i.e. cards originally ingested from Pokemon TCG API)."""
    from backend.app.models.asset import Asset
    from backend.app.models.game import Game

    subq = (
        select(
            Asset.id,
            Asset.metadata_json["provider_card_id"].astext.label("provider_card_id"),
        )
        .where(
            Asset.metadata_json.isnot(None),
            Asset.metadata_json["provider_card_id"].astext.isnot(None),
            Asset.metadata_json["provider_card_id"].astext != "",
            Asset.game == Game.POKEMON.value,
        )
        .subquery()
    )

    rows = session.execute(
        select(subq.c.provider_card_id)
        .outerjoin(
            PriceHistory,
            (PriceHistory.asset_id == subq.c.id)
            & (PriceHistory.source == primary_source),
        )
        .where(PriceHistory.id.is_(None))
        .limit(limit)
    ).all()

    return [row.provider_card_id for row in rows]


def _query_missing_image(session: Session, *, limit: int) -> list[str]:
    """Return provider_card_id values for assets whose metadata_json is missing
    a non-empty images.small URL."""
    from backend.app.models.asset import Asset
    from backend.app.models.game import Game

    rows = session.execute(
        select(
            Asset.metadata_json["provider_card_id"].astext.label("provider_card_id"),
        )
        .where(
            Asset.metadata_json.isnot(None),
            Asset.metadata_json["provider_card_id"].astext.isnot(None),
            Asset.metadata_json["provider_card_id"].astext != "",
            Asset.game == Game.POKEMON.value,
            ~(
                Asset.metadata_json.has_key("images")
                & Asset.metadata_json["images"].has_key("small")
                & (Asset.metadata_json["images"]["small"].astext != "")
            ),
        )
        .limit(limit)
    ).all()

    return [row.provider_card_id for row in rows]


def backfill_single_card(session: Session, asset: "Asset") -> bool:  # type: ignore[name-defined]
    """Re-fetch one asset from the Pokemon TCG API and fill its missing price/image.

    Returns True if a price point was inserted or an image was written; False
    otherwise (including on any exception — callers should not rely on raising).
    """
    from backend.app.models.asset import Asset as _Asset  # noqa: F401 (type guard)

    card_id: str | None = (asset.metadata_json or {}).get("provider_card_id")
    if not card_id:
        logger.warning(
            '{"event": "backfill_single_card_no_id", "asset_id": "%s"}', asset.id
        )
        return False

    ingested_at = datetime.now(UTC).replace(microsecond=0)
    from backend.app.services.backfill_retry_service import clear_backfill_failure

    try:
        with httpx.Client(timeout=20.0, headers=build_headers()) as client:
            card = fetch_card(client, card_id)
            chosen_price = choose_price_snapshot(card)
            if chosen_price is None:
                return False
            price_source, price_field, price = chosen_price
            asset_payload = build_asset_payload(card, price_source, price_field)
            _card_name = card.get("name", "")
            _pf = preflight_observation(_card_name)
            _normalised_name = _pf.normalised_title if not _pf.should_skip else _card_name
            observation_result = stage_observation_match(
                session,
                provider=POKEMON_TCG_PRICE_SOURCE,
                external_item_id=card["id"],
                raw_title=_normalised_name,
                raw_set_name=card.get("set", {}).get("name"),
                raw_card_number=card.get("number"),
                raw_language=extract_raw_language(card),
                asset_payload=asset_payload,
            )
            if not observation_result.can_write_price_history or observation_result.matched_asset is None:
                return False
            matched = observation_result.matched_asset
            had_image = bool((matched.metadata_json or {}).get("images", {}).get("small"))
            insert_result = add_price_point(
                session,
                asset_id=matched.id,
                source=POKEMON_TCG_PRICE_SOURCE,
                currency="USD",
                price=price,
                captured_at=ingested_at,
                market_segment='raw',
            )
            price_filled = insert_result.inserted
            has_image_now = bool((matched.metadata_json or {}).get("images", {}).get("small"))
            image_filled = not had_image and has_image_now
            clear_backfill_failure(session, matched.id)
            return price_filled or image_filled
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            '{"event": "backfill_single_card_error", "asset_id": "%s", "card_id": "%s", "error": "%s"}',
            asset.id,
            card_id,
            exc,
        )
        return False


def run_backfill_pass(session: Session) -> BackfillResult:
    """Re-fetch Pokemon TCG API data for assets missing a price or image.

    Queries assets whose provider_card_id is stored in metadata_json but whose
    PriceHistory (primary source) or image is missing, then re-runs them through
    the normal fetch + ingest path. Capped at settings.backfill_batch_size per run.
    """
    settings = get_settings()
    result = BackfillResult()
    batch_size = settings.backfill_batch_size

    missing_price_ids = _query_missing_price(
        session, limit=batch_size, primary_source=POKEMON_TCG_PRICE_SOURCE
    )
    missing_image_ids = _query_missing_image(session, limit=batch_size)

    result.missing_price = len(missing_price_ids)
    result.missing_image = len(missing_image_ids)

    # Deduplicate: a card may appear in both lists
    to_backfill = list(dict.fromkeys(missing_price_ids + missing_image_ids))[:batch_size]

    if not to_backfill:
        logger.info(
            '{"event": "backfill_skipped", "reason": "no_gaps_found"}'
        )
        return result

    logger.info(
        '{"event": "backfill_started", "missing_price": %d, "missing_image": %d, "to_backfill": %d}',
        result.missing_price,
        result.missing_image,
        len(to_backfill),
    )

    from backend.app.models.asset import Asset
    from backend.app.services.backfill_retry_service import record_backfill_failure

    assets = session.scalars(
        select(Asset).where(
            Asset.metadata_json["provider_card_id"].astext.in_(to_backfill)
        )
    ).all()
    asset_by_card_id = {
        (a.metadata_json or {}).get("provider_card_id"): a for a in assets
    }

    for card_id in to_backfill:
        result.attempted += 1
        asset = asset_by_card_id.get(card_id)
        if asset is None:
            result.errors += 1
            logger.warning(
                '{"event": "backfill_asset_not_found", "card_id": "%s"}', card_id
            )
            continue
        ok = backfill_single_card(session, asset)
        if ok:
            result.price_filled += 1
        else:
            result.errors += 1
            record_backfill_failure(
                session, asset.id, RuntimeError("backfill_single_card returned False")
            )

    logger.info(
        '{"event": "backfill_complete", "attempted": %d, "price_filled": %d, "image_filled": %d, "skipped_no_price": %d, "errors": %d}',
        result.attempted,
        result.price_filled,
        result.image_filled,
        result.skipped_no_price,
        result.errors,
    )
    return result
