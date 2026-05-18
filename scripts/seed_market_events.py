#!/usr/bin/env python3
"""seed_market_events.py  -  Seed curated Pokemon TCG market events for Phase 3 driver attribution.

Run: railway run python -m scripts.seed_market_events
     python -m scripts.seed_market_events   (local DB)

Events cover May 2025-May 2026. Dates marked VERIFY DATE are approximate and
must be confirmed by the operator before treating as attribution anchors.
Idempotent: existing rows (matched by description) are skipped.
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.models.predictions import MarketEvent


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


EVENTS = [
    # SET RELEASES
    {
        "event_date": _dt(2025, 6, 13),
        "event_type": "RELEASE",
        "description": "Twilight Masquerade (sv6) release  -  Bloodmoon Ursaluna ex SIR peak demand",
        "source_url": "https://www.pokemon.com/us/pokemon-tcg/product-line/sv6/",
        "affected_set_ids": ["Twilight Masquerade"],
        "affected_asset_ids": [],
        "expected_window_days": 21,
    },
    {
        "event_date": _dt(2025, 8, 2),
        "event_type": "RELEASE",
        "description": "Shrouded Fable (sv6.5) release  -  Pecharunt ex SIR, Darkrai ex SIR debut",
        "source_url": "https://www.pokemon.com/us/pokemon-tcg/product-line/sv6pt5/",
        "affected_set_ids": ["Shrouded Fable"],
        "affected_asset_ids": [],
        "expected_window_days": 14,
    },
    {
        "event_date": _dt(2025, 9, 12),
        "event_type": "RELEASE",
        "description": "Stellar Crown (sv7) release  -  Terapagos ex SIR debut",
        "source_url": "https://www.pokemon.com/us/pokemon-tcg/product-line/sv7/",
        "affected_set_ids": ["Stellar Crown"],
        "affected_asset_ids": [],
        "expected_window_days": 21,
    },
    {
        "event_date": _dt(2025, 11, 8),
        "event_type": "RELEASE",
        "description": "Surging Sparks (sv8) release  -  Pikachu ex SIR, Raichu ex SIR demand surge",
        "source_url": "https://www.pokemon.com/us/pokemon-tcg/product-line/sv8/",
        "affected_set_ids": ["Surging Sparks"],
        "affected_asset_ids": [],
        "expected_window_days": 21,
    },
    {
        "event_date": _dt(2026, 1, 17),
        "event_type": "RELEASE",
        "description": "Prismatic Evolutions (sv8pt5) release  -  Eevee SIR hits $200+, massive market event",
        "source_url": "https://www.pokemon.com/us/pokemon-tcg/product-line/sv8pt5/",
        "affected_set_ids": ["Prismatic Evolutions"],
        "affected_asset_ids": [],
        "expected_window_days": 30,
    },
    {
        "event_date": _dt(2026, 3, 28),
        "event_type": "RELEASE",
        "description": "Journey Together (sv9) release  -  Mew ex SIR, Mewtwo ex SIR debut",
        "source_url": "https://www.pokemon.com/us/pokemon-tcg/product-line/sv9/",
        "affected_set_ids": ["Journey Together"],
        "affected_asset_ids": [],
        "expected_window_days": 21,
    },
    {
        "event_date": _dt(2026, 5, 22),
        "event_type": "RELEASE",
        "description": "Chaos Rising release  -  Mega Greninja ex SIR, Mega Floette ex SIR debut",
        "source_url": None,
        "affected_set_ids": ["Chaos Rising"],
        "affected_asset_ids": [],
        "expected_window_days": 21,
    },
    {
        "event_date": _dt(2026, 5, 30),
        "event_type": "RELEASE",
        "description": "Destined Rivals (sv10) release",
        "source_url": None,
        "affected_set_ids": ["Destined Rivals"],
        "affected_asset_ids": [],
        "expected_window_days": 21,
    },
    # SUPPLY SHOCKS
    {
        "event_date": _dt(2025, 11, 15),  # VERIFY DATE
        "event_type": "SUPPLY",
        "description": "Destined Rivals reprint announcement  -  vintage card prices suppress on reprint fear",
        "source_url": None,
        "affected_set_ids": ["Destined Rivals"],
        "affected_asset_ids": [],
        "expected_window_days": 30,
    },
    {
        "event_date": _dt(2026, 2, 1),  # VERIFY DATE
        "event_type": "SUPPLY",
        "description": "Prismatic Evolutions restock announcement  -  Eevee SIR price correction from $200+ peak",
        "source_url": None,
        "affected_set_ids": ["Prismatic Evolutions"],
        "affected_asset_ids": [],
        "expected_window_days": 14,
    },
    {
        "event_date": _dt(2026, 3, 15),  # VERIFY DATE
        "event_type": "SUPPLY",
        "description": "Evolving Skies reprint announcement  -  Rayquaza VMAX, Umbreon VMAX price drop",
        "source_url": None,
        "affected_set_ids": ["Evolving Skies"],
        "affected_asset_ids": [],
        "expected_window_days": 21,
    },
    {
        "event_date": _dt(2025, 10, 1),  # VERIFY DATE
        "event_type": "SUPPLY",
        "description": "PSA grading population milestone  -  Charizard base shadowless PSA 10 pop exceeds 1000",
        "source_url": None,
        "affected_set_ids": ["Base Set"],
        "affected_asset_ids": [],
        "expected_window_days": 7,
    },
    {
        "event_date": _dt(2026, 4, 15),  # VERIFY DATE
        "event_type": "SUPPLY",
        "description": "PSA April 2026 population report  -  Pikachu ex SIR Surging Sparks pop shock",
        "source_url": None,
        "affected_set_ids": ["Surging Sparks"],
        "affected_asset_ids": [],
        "expected_window_days": 7,
    },
    # TOURNAMENT EVENTS
    {
        "event_date": _dt(2025, 8, 14),
        "event_type": "TOURNAMENT",
        "description": "2025 Pokemon World Championships  -  Anaheim CA, drives meta-relevant card demand",
        "source_url": "https://worlds.pokemon.com/en-us/",
        "affected_set_ids": [],
        "affected_asset_ids": [],
        "expected_window_days": 14,
    },
    {
        "event_date": _dt(2025, 9, 28),  # VERIFY DATE
        "event_type": "TOURNAMENT",
        "description": "North American International Championships 2025  -  meta rotation impact",
        "source_url": None,
        "affected_set_ids": [],
        "affected_asset_ids": [],
        "expected_window_days": 7,
    },
    {
        "event_date": _dt(2026, 4, 19),  # VERIFY DATE
        "event_type": "TOURNAMENT",
        "description": "Spring 2026 Regionals  -  first major with Journey Together legal",
        "source_url": None,
        "affected_set_ids": ["Journey Together"],
        "affected_asset_ids": [],
        "expected_window_days": 7,
    },
    # INFLUENCER EVENTS  -  dates are approximate, VERIFY before use as attribution anchors
    {
        "event_date": _dt(2025, 7, 20),  # VERIFY DATE
        "event_type": "INFLUENCER",
        "description": "Logan Paul Pokemon card opening at public event  -  vintage demand spike",
        "source_url": None,
        "affected_set_ids": ["Base Set", "Base Set 2"],
        "affected_asset_ids": [],
        "expected_window_days": 14,
    },
    {
        "event_date": _dt(2025, 10, 15),  # VERIFY DATE
        "event_type": "INFLUENCER",
        "description": "MrBeast Pokemon box break video  -  mass market exposure drives broad demand",
        "source_url": None,
        "affected_set_ids": [],
        "affected_asset_ids": [],
        "expected_window_days": 7,
    },
    {
        "event_date": _dt(2026, 1, 25),  # VERIFY DATE
        "event_type": "INFLUENCER",
        "description": "High-profile celebrity Pokemon collection publicized  -  vintage holo demand spike",
        "source_url": None,
        "affected_set_ids": ["Base Set"],
        "affected_asset_ids": [],
        "expected_window_days": 7,
    },
    {
        "event_date": _dt(2026, 3, 20),  # VERIFY DATE
        "event_type": "INFLUENCER",
        "description": "Pokemon YouTuber coordinated box break series  -  Chaos Rising pre-release hype",
        "source_url": None,
        "affected_set_ids": ["Chaos Rising"],
        "affected_asset_ids": [],
        "expected_window_days": 7,
    },
    {
        "event_date": _dt(2026, 4, 10),  # VERIFY DATE
        "event_type": "INFLUENCER",
        "description": "Prismatic Evolutions Eevee cards featured in mainstream media coverage",
        "source_url": None,
        "affected_set_ids": ["Prismatic Evolutions"],
        "affected_asset_ids": [],
        "expected_window_days": 5,
    },
]


def seed(db: Session) -> int:
    """Insert events not already in DB (matched by description). Returns count inserted."""
    existing = set(db.scalars(select(MarketEvent.description)).all())
    inserted = 0
    for e in EVENTS:
        if e["description"] in existing:
            print(f"  skip (exists): {e['description'][:70]}")
            continue
        event = MarketEvent(
            event_date=e["event_date"],
            event_type=e["event_type"],
            description=e["description"],
            source_url=e.get("source_url"),
            affected_set_ids=e.get("affected_set_ids", []),
            affected_asset_ids=e.get("affected_asset_ids", []),
            expected_window_days=e.get("expected_window_days"),
        )
        db.add(event)
        inserted += 1
        print(f"  insert: {e['event_type']:12s} {e['event_date'].date()}  -  {e['description'][:70]}")
    db.commit()
    return inserted


def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    with Session(engine) as db:
        n = seed(db)
    total = len(EVENTS)
    print(f"\nDone. Inserted {n} new events. {total - n} skipped (already existed).")


if __name__ == "__main__":
    main()
