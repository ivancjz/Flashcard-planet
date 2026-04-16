import json

from backend.app.core.tracked_pools import HIGH_ACTIVITY_V2_POOL_KEY, get_tracked_pokemon_pools
from backend.app.db.init_db import init_db
from backend.app.db.session import SessionLocal
from backend.app.ingestion.pokemon_tcg import ingest_pokemon_tcg_cards
from backend.app.services.diagnostics_summary_service import build_standardized_diagnostics_summary


def ingest() -> None:
    init_db()
    pools = {pool.key: pool for pool in get_tracked_pokemon_pools()}
    high_activity_v2_pool = pools.get(HIGH_ACTIVITY_V2_POOL_KEY)
    if high_activity_v2_pool is None:
        raise RuntimeError("No High-Activity v2 pool is configured in POKEMON_TCG_HIGH_ACTIVITY_V2_CARD_IDS.")

    with SessionLocal() as session:
        result = ingest_pokemon_tcg_cards(session, card_ids=high_activity_v2_pool.card_ids)
        summary = build_standardized_diagnostics_summary(
            session,
            scope_key=high_activity_v2_pool.key,
            scope_label=high_activity_v2_pool.label,
        )

    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    ingest()
