"""Import Pokemon TCG cards into the assets table.

Usage examples:
    python scripts/import_pokemon_cards.py --set-id base1
    python scripts/import_pokemon_cards.py --all-sets --limit 100
    python scripts/import_pokemon_cards.py --set-id sv3pt5 --api-key YOUR_API_KEY
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests
from requests import Response
from sqlalchemy import inspect, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import get_settings
from backend.app.core.price_sources import POKEMON_TCG_PRICE_SOURCE
from backend.app.db.session import SessionLocal
from backend.app.ingestion.pokemon_tcg import (
    MAX_FETCH_ATTEMPTS,
    RETRYABLE_STATUS_CODES,
    build_headers,
    choose_price_snapshot,
    parse_release_year,
)
from backend.app.models.asset import Asset

try:
    from backend.app.models.price_history import PriceHistory
except Exception:  # pragma: no cover - defensive fallback for schema variance
    PriceHistory = None


logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 250
DEFAULT_BATCH_SIZE = 200
DEFAULT_PAGE_SLEEP_SECONDS = 0.2
SET_ID_ALIASES: dict[str, str] = {
    "jungle": "base2",
    "fossil": "base3",
    "base-set-2": "base4",
    "team-rocket": "base5",
    "gym-heroes": "gym1",
    "gym-challenge": "gym2",
    "neo-genesis": "neo1",
    "neo-discovery": "neo2",
    "neo-revelation": "neo3",
    "neo-destiny": "neo4",
    "sv151": "sv3pt5",
    "prismatic-evolutions": "sv8pt5",
}


@dataclass
class ImportSummary:
    sets_processed: int = 0
    cards_seen: int = 0
    cards_processed: int = 0
    prices_recorded: int = 0


class PokemonTCGImporter:
    def __init__(self, *, api_key: str | None, limit: int | None) -> None:
        settings = get_settings()
        self.base_url = settings.pokemon_tcg_api_base_url.rstrip("/")
        self.limit = limit
        self.session = requests.Session()
        headers = build_headers()
        if api_key:
            headers["X-Api-Key"] = api_key
        self.session.headers.update(headers)
        self.summary = ImportSummary()
        self._run_captured_at = datetime.now(UTC).replace(microsecond=0)

    def fetch_sets(self, set_id: str | None, include_all: bool) -> list[dict[str, Any]]:
        if set_id:
            payload = self._get_json(
                "/sets",
                params={
                    "q": f"id:{set_id}",
                    "page": 1,
                    "pageSize": 1,
                    "orderBy": "releaseDate",
                },
            )
            sets = payload.get("data", [])
            if not sets:
                raise ValueError(f"Pokemon TCG API returned no set for set id {set_id!r}.")
            return sets

        if not include_all:
            raise ValueError("Either --set-id or --all-sets is required.")

        sets: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self._get_json(
                "/sets",
                params={
                    "page": page,
                    "pageSize": DEFAULT_PAGE_SIZE,
                    "orderBy": "releaseDate",
                },
            )
            batch = payload.get("data", [])
            if not batch:
                break
            sets.extend(batch)

            total_count = int(payload.get("totalCount") or 0)
            page_size = int(payload.get("pageSize") or DEFAULT_PAGE_SIZE)
            count = int(payload.get("count") or len(batch))
            if len(sets) >= total_count or count < page_size:
                break
            page += 1

        return sets

    def fetch_cards_for_set(self, set_id: str) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        page = 1

        while True:
            remaining = self._remaining_capacity()
            if remaining == 0:
                break

            page_size = DEFAULT_PAGE_SIZE
            if remaining is not None:
                page_size = min(page_size, remaining)

            payload = self._get_json(
                "/cards",
                params={
                    "q": f"set.id:{set_id}",
                    "page": page,
                    "pageSize": page_size,
                    "orderBy": "number",
                },
            )
            batch = payload.get("data", [])
            if not batch:
                break

            cards.extend(batch)
            self.summary.cards_seen += len(batch)

            total_count = int(payload.get("totalCount") or 0)
            count = int(payload.get("count") or len(batch))
            current_page_size = int(payload.get("pageSize") or page_size)

            if self._remaining_capacity() == 0:
                break
            if len(cards) >= total_count or count < current_page_size:
                break
            page += 1

        return cards

    def _remaining_capacity(self) -> int | None:
        if self.limit is None:
            return None
        return max(self.limit - self.summary.cards_seen, 0)

    def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        last_error: Exception | None = None

        for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
            try:
                response = self.session.get(url, params=params, timeout=30)
                if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_FETCH_ATTEMPTS:
                    self._sleep_for_retry(response, attempt)
                    continue
                response.raise_for_status()
                payload = response.json()
                self._sleep_after_page(response)
                return payload
            except requests.HTTPError as exc:
                last_error = exc
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code in RETRYABLE_STATUS_CODES and attempt < MAX_FETCH_ATTEMPTS:
                    self._sleep_for_retry(exc.response, attempt)
                    continue
                raise
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_error = exc
                if attempt < MAX_FETCH_ATTEMPTS:
                    delay = min(2 ** (attempt - 1), 8)
                    logger.warning(
                        "Retrying %s after network error on attempt %s/%s: %s",
                        url,
                        attempt,
                        MAX_FETCH_ATTEMPTS,
                        exc,
                    )
                    time.sleep(delay)
                    continue
                raise

        raise RuntimeError(f"Failed to fetch {url}") from last_error

    def _sleep_for_retry(self, response: Response | None, attempt: int) -> None:
        retry_after = self._parse_retry_after_seconds(response)
        delay = retry_after if retry_after is not None else min(2 ** (attempt - 1), 8)
        logger.warning(
            "Pokemon TCG API rate-limited or transiently failed; sleeping %.2fs before retry %s/%s.",
            delay,
            attempt + 1,
            MAX_FETCH_ATTEMPTS,
        )
        time.sleep(delay)

    def _sleep_after_page(self, response: Response) -> None:
        delay = DEFAULT_PAGE_SLEEP_SECONDS

        retry_after = self._parse_retry_after_seconds(response)
        if retry_after is not None:
            delay = max(delay, retry_after)

        remaining_header = response.headers.get("X-RateLimit-Remaining")
        reset_header = response.headers.get("X-RateLimit-Reset")
        if remaining_header is not None and reset_header is not None:
            try:
                remaining = int(float(remaining_header))
                reset_epoch = int(float(reset_header))
            except ValueError:
                remaining = None
                reset_epoch = None
            if remaining is not None and reset_epoch is not None and remaining <= 1:
                reset_delay = max(reset_epoch - int(time.time()), 0)
                delay = max(delay, float(reset_delay))

        if delay > 0:
            time.sleep(delay)

    @staticmethod
    def _parse_retry_after_seconds(response: Response | None) -> float | None:
        if response is None:
            return None
        retry_after = response.headers.get("Retry-After")
        if retry_after is None:
            return None
        try:
            return max(float(retry_after), 0.0)
        except ValueError:
            return None

    def close(self) -> None:
        self.session.close()


def derive_variant(card: dict[str, Any]) -> str | None:
    values: list[str] = []
    for subtype in card.get("subtypes") or []:
        normalized = str(subtype).strip()
        if normalized and normalized not in values:
            values.append(normalized)

    rarity = (card.get("rarity") or "").strip()
    if rarity and rarity not in values:
        values.append(rarity)

    if values:
        return " | ".join(values)
    return None


def build_asset_payload(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_class": "TCG",
        "game": "pokemon",
        "name": card["name"],
        "set_name": (card.get("set") or {}).get("name"),
        "card_number": card.get("number"),
        "year": parse_release_year(card),
        "language": "EN",
        "variant": derive_variant(card),
        "grade_company": None,
        "grade_score": None,
        "external_id": card["id"],
        "metadata_json": {
            "provider": POKEMON_TCG_PRICE_SOURCE,
            "pokemon_tcg_card_id": card["id"],
            "set_id": (card.get("set") or {}).get("id"),
            "release_date": (card.get("set") or {}).get("releaseDate"),
            "set": {
                "id": (card.get("set") or {}).get("id"),
                "name": (card.get("set") or {}).get("name"),
                "total": (card.get("set") or {}).get("total"),
            },
            "rarity": card.get("rarity"),
            "subtypes": card.get("subtypes") or [],
            "supertype": card.get("supertype"),
            "images": card.get("images") or {},
            "tcgplayer_url": (card.get("tcgplayer") or {}).get("url"),
        },
        "notes": "Imported by scripts/import_pokemon_cards.py.",
    }


def build_price_payload(
    card: dict[str, Any],
    *,
    captured_at: datetime,
) -> dict[str, Any] | None:
    if PriceHistory is None:
        return None

    chosen = choose_price_snapshot(card)
    if chosen is None:
        return None

    _price_type, _price_field, price = chosen
    if price is None:
        return None

    return {
        "external_id": card["id"],
        "source": POKEMON_TCG_PRICE_SOURCE,
        "currency": "USD",
        "price": Decimal(str(price)),
        "captured_at": captured_at,
    }


def flush_batch(
    session,
    *,
    asset_payloads: list[dict[str, Any]],
    price_payloads: list[dict[str, Any]],
) -> tuple[int, int]:
    if not asset_payloads:
        return 0, 0

    # Deduplicate by external_id — PostgreSQL raises CardinalityViolation if the
    # same conflict-key appears twice in a single ON CONFLICT DO UPDATE batch.
    seen: dict[str, dict] = {}
    for payload in asset_payloads:
        seen[payload["external_id"]] = payload
    asset_payloads = list(seen.values())

    external_ids = [payload["external_id"] for payload in asset_payloads]

    try:
        insert_statement = pg_insert(Asset).values(asset_payloads)
        upsert_statement = insert_statement.on_conflict_do_update(
            index_elements=[Asset.external_id],
            set_={"metadata": insert_statement.excluded.metadata},
        )
        session.execute(upsert_statement)

        external_id_to_asset_id = dict(
            session.execute(
                select(Asset.external_id, Asset.id).where(Asset.external_id.in_(external_ids))
            ).all()
        )

        prices_recorded = 0
        if price_payloads and PriceHistory is not None:
            rows = []
            seen_asset_ids: set[Any] = set()
            for payload in price_payloads:
                asset_id = external_id_to_asset_id.get(payload["external_id"])
                if asset_id is None:
                    continue
                if asset_id in seen_asset_ids:
                    continue
                seen_asset_ids.add(asset_id)
                rows.append(
                    PriceHistory(
                        asset_id=asset_id,
                        source=payload["source"],
                        currency=payload["currency"],
                        price=payload["price"],
                        captured_at=payload["captured_at"],
                    )
                )

            if rows:
                existing_asset_ids = set(
                    session.scalars(
                        select(PriceHistory.asset_id).where(
                            PriceHistory.asset_id.in_([row.asset_id for row in rows]),
                            PriceHistory.source == POKEMON_TCG_PRICE_SOURCE,
                            PriceHistory.captured_at == rows[0].captured_at,
                        )
                    ).all()
                )
                rows_to_add = [row for row in rows if row.asset_id not in existing_asset_ids]
                if rows_to_add:
                    session.add_all(rows_to_add)
                    prices_recorded = len(rows_to_add)

        session.commit()
        # rowcount is -1 for ON CONFLICT DO NOTHING on PostgreSQL/psycopg — use batch size instead.
        cards_processed = len(asset_payloads)
        return cards_processed, prices_recorded
    except SQLAlchemyError:
        session.rollback()
        logger.exception("Database write failed while importing Pokemon cards.")
        raise


def price_history_available(session) -> bool:
    if PriceHistory is None:
        return False
    try:
        return bool(inspect(session.bind).has_table(PriceHistory.__tablename__))
    except SQLAlchemyError:
        logger.warning("Could not confirm price_history table availability; skipping price inserts.")
        return False


PROGRESS_INTERVAL = 50


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import Pokemon card assets from the Pokemon TCG API.")
    scope = parser.add_mutually_exclusive_group(required=False)
    scope.add_argument("--set-id", type=str, help="Fetch cards from a single Pokemon TCG set.")
    scope.add_argument(
        "--set-ids",
        type=str,
        help="Comma-separated list of set IDs to import in order (e.g. swsh7,swsh11,sm115).",
    )
    scope.add_argument("--all-sets", action="store_true", help="Fetch cards from every set in the API.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch from API and count cards/prices but do not write to the database.",
    )
    parser.add_argument(
        "--list-aliases",
        action="store_true",
        help="Print supported set id aliases and exit.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Cap the total number of cards fetched.")
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Optional Pokemon TCG API key. Overrides configured settings for this run.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity.",
    )
    args = parser.parse_args()
    if args.list_aliases:
        print("Set ID aliases:")
        for alias, real_id in SET_ID_ALIASES.items():
            print(f"  {alias} -> {real_id}")
        sys.exit(0)
    if not args.set_id and not args.set_ids and not args.all_sets:
        parser.error("one of the arguments --set-id/--set-ids/--all-sets is required")
    if args.set_id and args.set_id.lower() in SET_ID_ALIASES:
        resolved = SET_ID_ALIASES[args.set_id.lower()]
        print(f"Resolving set alias '{args.set_id}' -> '{resolved}'")
        args.set_id = resolved
    if args.set_ids:
        resolved_ids = []
        for sid in args.set_ids.split(","):
            sid = sid.strip()
            if not sid:
                continue
            if sid.lower() in SET_ID_ALIASES:
                resolved = SET_ID_ALIASES[sid.lower()]
                print(f"Resolving set alias '{sid}' -> '{resolved}'")
                sid = resolved
            resolved_ids.append(sid)
        args.set_ids = resolved_ids
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be a positive integer.")
    return args


def _process_set(
    importer: "PokemonTCGImporter",
    session: Any,
    set_id: str,
    *,
    can_record_prices: bool,
    dry_run: bool,
    asset_batch: list,
    price_batch: list,
    explicit_set_id: bool = False,
) -> None:
    logger.info("Fetching cards for set %s.", set_id)
    cards = importer.fetch_cards_for_set(set_id)
    if not cards:
        if explicit_set_id:
            raise ValueError(
                f"No cards returned for set {set_id!r}; the set ID may be invalid or misspelled."
            )
        logger.info("No cards returned for set %s.", set_id)
        return

    importer.summary.sets_processed += 1
    cards_in_set = len(cards)
    prices_in_set = sum(1 for c in cards if build_price_payload(c, captured_at=importer._run_captured_at) is not None)

    if dry_run:
        # cards_seen already incremented inside fetch_cards_for_set — don't add again
        print(
            f"  [dry-run] {set_id}: {cards_in_set} cards fetched, "
            f"~{prices_in_set} would have price records"
        )
        return

    for i, card in enumerate(cards):
        asset_batch.append(build_asset_payload(card))
        if can_record_prices:
            price_payload = build_price_payload(card, captured_at=importer._run_captured_at)
            if price_payload is not None:
                price_batch.append(price_payload)

        if (i + 1) % PROGRESS_INTERVAL == 0:
            print(f"  {set_id}: {i + 1}/{cards_in_set} cards prepared...")

        if len(asset_batch) >= DEFAULT_BATCH_SIZE:
            cards_processed, prices_recorded = flush_batch(
                session,
                asset_payloads=asset_batch,
                price_payloads=price_batch,
            )
            importer.summary.cards_processed += cards_processed
            importer.summary.prices_recorded += prices_recorded
            logger.info(
                "Committed batch: assets_inserted=%s prices_recorded=%s total_seen=%s",
                cards_processed,
                prices_recorded,
                importer.summary.cards_seen,
            )
            asset_batch.clear()
            price_batch.clear()

    print(f"  {set_id}: done ({cards_in_set} cards).")


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    dry_run: bool = args.dry_run
    if dry_run:
        print("DRY RUN — no database writes will occur.")

    importer = PokemonTCGImporter(api_key=args.api_key, limit=args.limit)

    asset_batch: list[dict[str, Any]] = []
    price_batch: list[dict[str, Any]] = []

    with SessionLocal() as session:
        can_record_prices = False if dry_run else price_history_available(session)
        if not can_record_prices and not dry_run:
            logger.warning("price_history model or table is unavailable; price ingestion will be skipped.")

        try:
            if args.set_ids:
                # Multi-set mode: iterate explicitly, no fetch_sets() call needed.
                for set_id in args.set_ids:
                    if importer._remaining_capacity() == 0:
                        break
                    _process_set(
                        importer, session, set_id,
                        can_record_prices=can_record_prices,
                        dry_run=dry_run,
                        asset_batch=asset_batch,
                        price_batch=price_batch,
                        explicit_set_id=True,
                    )
            else:
                sets = importer.fetch_sets(args.set_id, args.all_sets)
                logger.info("Fetched %s set definition(s) from the Pokemon TCG API.", len(sets))
                for card_set in sets:
                    if importer._remaining_capacity() == 0:
                        break
                    _process_set(
                        importer, session, card_set["id"],
                        can_record_prices=can_record_prices,
                        dry_run=dry_run,
                        asset_batch=asset_batch,
                        price_batch=price_batch,
                    )

            if asset_batch and not dry_run:
                cards_processed, prices_recorded = flush_batch(
                    session,
                    asset_payloads=asset_batch,
                    price_payloads=price_batch,
                )
                importer.summary.cards_processed += cards_processed
                importer.summary.prices_recorded += prices_recorded
                logger.info(
                    "Committed final batch: assets_inserted=%s prices_recorded=%s total_seen=%s",
                    cards_processed,
                    prices_recorded,
                    importer.summary.cards_seen,
                )
        finally:
            importer.close()

    if dry_run:
        print(
            f"\nDry-run summary: sets_scanned={importer.summary.sets_processed}, "
            f"cards_seen={importer.summary.cards_seen} — no DB writes."
        )
    else:
        print(
            "Import summary: "
            f"sets processed={importer.summary.sets_processed}, "
            f"cards upserted={importer.summary.cards_processed}, "
            f"prices recorded={importer.summary.prices_recorded}"
        )


if __name__ == "__main__":
    main()
