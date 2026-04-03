from __future__ import annotations

import argparse
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select

from backend.app.core.config import get_settings
from backend.app.db.init_db import init_db
from backend.app.db.session import SessionLocal
from backend.app.ingestion.pokemon_tcg import parse_card_ids
from backend.app.models.alert import Alert
from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory
from backend.app.models.watchlist import Watchlist


@dataclass
class LegacyPokemonAsset:
    asset_id: uuid.UUID
    name: str
    card_id: str
    external_id: str
    price_history_rows: int
    latest_captured_at: datetime | None
    watchlist_rows: int
    alert_rows: int


def get_tracked_card_ids() -> set[str]:
    settings = get_settings()
    return set(parse_card_ids(settings.pokemon_tcg_card_ids))


def get_legacy_pokemon_assets() -> tuple[list[LegacyPokemonAsset], set[str]]:
    tracked_card_ids = get_tracked_card_ids()

    with SessionLocal() as session:
        pokemon_assets = session.scalars(
            select(Asset)
            .where(Asset.external_id.is_not(None))
            .where(Asset.external_id.like("pokemontcg:%"))
            .order_by(Asset.name.asc(), Asset.external_id.asc())
        ).all()

        legacy_assets: list[LegacyPokemonAsset] = []
        for asset in pokemon_assets:
            parts = (asset.external_id or "").split(":")
            card_id = parts[1] if len(parts) > 1 else ""
            if card_id in tracked_card_ids:
                continue

            price_history_rows = int(
                session.scalar(
                    select(func.count(PriceHistory.id)).where(PriceHistory.asset_id == asset.id)
                )
                or 0
            )
            latest_captured_at = session.scalar(
                select(func.max(PriceHistory.captured_at)).where(PriceHistory.asset_id == asset.id)
            )
            watchlist_rows = int(
                session.scalar(select(func.count(Watchlist.id)).where(Watchlist.asset_id == asset.id))
                or 0
            )
            alert_rows = int(
                session.scalar(select(func.count(Alert.id)).where(Alert.asset_id == asset.id)) or 0
            )

            legacy_assets.append(
                LegacyPokemonAsset(
                    asset_id=asset.id,
                    name=asset.name,
                    card_id=card_id,
                    external_id=asset.external_id or "",
                    price_history_rows=price_history_rows,
                    latest_captured_at=latest_captured_at,
                    watchlist_rows=watchlist_rows,
                    alert_rows=alert_rows,
                )
            )

    return legacy_assets, tracked_card_ids


def print_preview(legacy_assets: list[LegacyPokemonAsset], tracked_card_ids: set[str]) -> None:
    print(f"Tracked Pokemon card ids loaded from settings: {len(tracked_card_ids)}")
    if not legacy_assets:
        print("No legacy Pokemon assets found outside the current tracked card list.")
        return

    print(f"Legacy Pokemon assets outside the current tracked card list: {len(legacy_assets)}")
    for asset in legacy_assets:
        latest_captured_at = (
            asset.latest_captured_at.isoformat() if asset.latest_captured_at else "<none>"
        )
        print(
            f"- {asset.name} [{asset.card_id}] external_id={asset.external_id} "
            f"price_history_rows={asset.price_history_rows} "
            f"latest_captured_at={latest_captured_at} "
            f"watchlists={asset.watchlist_rows} alerts={asset.alert_rows}"
        )


def apply_cleanup(legacy_assets: list[LegacyPokemonAsset]) -> None:
    if not legacy_assets:
        print("No cleanup needed.")
        return

    deleted_assets = 0
    deleted_price_history_rows = 0
    skipped_assets: list[str] = []

    with SessionLocal() as session:
        for legacy_asset in legacy_assets:
            if legacy_asset.watchlist_rows or legacy_asset.alert_rows:
                skipped_assets.append(
                    f"{legacy_asset.name} [{legacy_asset.card_id}] "
                    f"(watchlists={legacy_asset.watchlist_rows}, alerts={legacy_asset.alert_rows})"
                )
                continue

            asset = session.get(Asset, legacy_asset.asset_id)
            if asset is None:
                continue

            deleted_assets += 1
            deleted_price_history_rows += legacy_asset.price_history_rows
            session.delete(asset)

        session.commit()

    print(
        "Legacy Pokemon cleanup complete: "
        f"deleted_assets={deleted_assets}, "
        f"deleted_price_history_rows={deleted_price_history_rows}"
    )
    if skipped_assets:
        print("Skipped assets with dependent watchlists or alerts:")
        for skipped_asset in skipped_assets:
            print(f"- {skipped_asset}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Preview or clean legacy Pokemon assets that are no longer in the current "
            "POKEMON_TCG_CARD_IDS setting."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete legacy Pokemon assets that have no watchlists or alerts.",
    )
    args = parser.parse_args()

    init_db()
    legacy_assets, tracked_card_ids = get_legacy_pokemon_assets()
    print_preview(legacy_assets, tracked_card_ids)

    if args.apply:
        apply_cleanup(legacy_assets)


if __name__ == "__main__":
    main()
