from __future__ import annotations

import json

from backend.app.db.init_db import init_db
from backend.app.db.session import SessionLocal
from backend.app.ingestion.ebay_sold import ingest_ebay_sold_cards
from backend.app.services.diagnostics_summary_service import build_standardized_diagnostics_summary


def ingest() -> None:
    init_db()
    with SessionLocal() as session:
        result = ingest_ebay_sold_cards(session)
        summary = build_standardized_diagnostics_summary(
            session,
            ingestion_result=result,
            scope_key="ebay_sold_keywords",
            scope_label="Configured eBay Search Keywords",
        )

    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    ingest()
