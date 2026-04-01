from backend.app.db.init_db import init_db
from backend.app.db.session import SessionLocal
from backend.app.ingestion.pokemon_tcg import ingest_pokemon_tcg_cards


def ingest() -> None:
    init_db()
    with SessionLocal() as session:
        result = ingest_pokemon_tcg_cards(session)

    print(
        "Pokemon TCG ingestion complete: "
        f"cards_processed={result.cards_processed}, "
        f"assets_created={result.assets_created}, "
        f"assets_updated={result.assets_updated}, "
        f"price_points_inserted={result.price_points_inserted}, "
        f"sample_rows_deleted={result.sample_rows_deleted}"
    )


if __name__ == "__main__":
    ingest()
