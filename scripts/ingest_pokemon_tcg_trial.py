import json

from backend.app.core.tracked_pools import TRIAL_POOL_KEY, get_tracked_pokemon_pools
from backend.app.db.init_db import init_db
from backend.app.db.session import SessionLocal
from backend.app.ingestion.pokemon_tcg import ingest_pokemon_tcg_cards
from backend.app.services.diagnostics_summary_service import build_standardized_diagnostics_summary


def ingest() -> None:
    init_db()
    pools = {pool.key: pool for pool in get_tracked_pokemon_pools()}
    trial_pool = pools.get(TRIAL_POOL_KEY)
    if trial_pool is None:
        raise RuntimeError("No trial pool is configured in POKEMON_TCG_TRIAL_CARD_IDS.")

    with SessionLocal() as session:
        result = ingest_pokemon_tcg_cards(session, card_ids=trial_pool.card_ids)
        summary = build_standardized_diagnostics_summary(
            session,
            scope_key=trial_pool.key,
            scope_label=trial_pool.label,
        )

    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    ingest()
