import json

from backend.app.db.init_db import init_db
from backend.app.db.session import SessionLocal
from backend.app.ingestion.pokemon_tcg import ingest_game_cards
from backend.app.services.diagnostics_summary_service import build_standardized_diagnostics_summary


def ingest() -> None:
    init_db()
    with SessionLocal() as session:
        result = ingest_game_cards(session)
        summary = build_standardized_diagnostics_summary(
            session,
            scope_key="configured_cards",
            scope_label="Configured Card Universe",
        )

    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    ingest()
