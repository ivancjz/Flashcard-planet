from backend.app.core.tracked_pools import TRIAL_POOL_KEY, get_tracked_pokemon_pools
from backend.app.db.init_db import init_db
from backend.app.db.session import SessionLocal
from backend.app.ingestion.pokemon_tcg import ingest_pokemon_tcg_cards
from backend.app.services.data_health_service import get_data_health_report


def ingest() -> None:
    init_db()
    pools = {pool.key: pool for pool in get_tracked_pokemon_pools()}
    trial_pool = pools.get(TRIAL_POOL_KEY)
    if trial_pool is None:
        raise RuntimeError("No trial pool is configured in POKEMON_TCG_TRIAL_CARD_IDS.")

    with SessionLocal() as session:
        result = ingest_pokemon_tcg_cards(session, card_ids=trial_pool.card_ids)
        report = get_data_health_report(session)

    print(
        "Pokemon TCG trial pool ingestion complete: "
        f"pool={trial_pool.label}, "
        f"cards_requested={result.cards_requested}, "
        f"cards_processed={result.cards_processed}, "
        f"cards_failed={result.cards_failed}, "
        f"cards_skipped_no_price={result.cards_skipped_no_price}, "
        f"assets_created={result.assets_created}, "
        f"assets_updated={result.assets_updated}, "
        f"price_points_inserted={result.price_points_inserted}, "
        f"price_points_changed={result.price_points_changed}, "
        f"price_points_unchanged={result.price_points_unchanged}, "
        f"price_points_skipped_existing_timestamp={result.price_points_skipped_existing_timestamp}, "
        f"sample_rows_deleted={result.sample_rows_deleted}, "
        f"latest_captured_at={result.latest_captured_at.isoformat() if result.latest_captured_at else '<none>'}, "
        f"inserted_assets={', '.join(result.inserted_asset_names) if result.inserted_asset_names else '<none>'}"
    )
    print(
        "Tracked Pokemon data health snapshot: "
        f"total_assets={report.total_assets}, "
        f"assets_with_real_history={report.assets_with_real_history}, "
        f"average_real_history_points_per_asset={report.average_real_history_points_per_asset}, "
        f"assets_lt3={report.assets_with_fewer_than_3_real_points}, "
        f"assets_lt5={report.assets_with_fewer_than_5_real_points}, "
        f"assets_lt8={report.assets_with_fewer_than_8_real_points}, "
        f"recent_real_rows_24h={report.recent_real_price_rows_last_24h}, "
        f"assets_changed_24h={report.assets_with_price_change_last_24h}, "
        f"assets_changed_7d={report.assets_with_price_change_last_7d}, "
        f"recent_changed_row_pct_24h={report.percent_recent_rows_changed_last_24h}, "
        f"recent_changed_row_pct_7d={report.percent_recent_rows_changed_last_7d}, "
        f"full_history_no_movement_assets={report.assets_with_no_price_movement_full_history}, "
        f"unchanged_latest_assets={report.assets_with_unchanged_latest_price}"
    )


if __name__ == "__main__":
    ingest()
