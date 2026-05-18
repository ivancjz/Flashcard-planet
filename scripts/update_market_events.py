#!/usr/bin/env python3
"""One-shot script: apply verified market_events corrections from 2026-05-19 research.

Run: railway run --service Flashcard-planet python -m scripts.update_market_events
"""
import os
import sys
from sqlalchemy import create_engine, text

engine = create_engine(os.environ["DATABASE_URL"])

updates = [
    # Event 1: Logan Paul verified date + source
    (
        "Event 1 — Logan Paul box break",
        text("""
            UPDATE market_events SET
                event_date = '2026-02-15',
                description = 'Logan Paul + Goldin 1st Edition Base Set box break ($1.38M pack sales) - vintage Pokemon demand spike',
                source_url = 'https://www.cllct.com/sports-collectibles/sports-cards/packs-in-logan-paul-1st-edition-pokemon-break-sell-for-combined-1-38-million'
            WHERE description LIKE '%Logan Paul Pokemon card opening%'
        """),
    ),
    # Event 2: MrBeast → verified Whatnot event
    (
        "Event 2 — MrBeast x Whatnot",
        text("""
            UPDATE market_events SET
                event_date = '2026-02-08',
                description = 'MrBeast x Whatnot Big Game livestream - $1M+ giveaway including Base Set Booster Box, Charizard PSA 10',
                source_url = 'https://www.actionfigureinsider.com/mrbeast-x-whatnot-super-bowl-livestream-giving-away-rare-pokemon-cards-49ers-sb-ring-and-more/'
            WHERE description LIKE '%MrBeast Pokemon box break%'
        """),
    ),
    # Event 3: Pikachu Illustrator relisting
    (
        "Event 3 — Pikachu Illustrator",
        text("""
            UPDATE market_events SET
                event_date = '2026-01-26',
                description = 'Logan Paul Pikachu Illustrator PSA 10 relisted at Goldin (record $5.275M purchase, bidding > $6.3M)',
                source_url = 'https://www.cllct.com/sports-collectibles/sports-cards/packs-in-logan-paul-1st-edition-pokemon-break-sell-for-combined-1-38-million'
            WHERE description LIKE '%celebrity Pokemon collection%'
        """),
    ),
    # Event 4a: Chaos Rising announcement
    (
        "Event 4a — Chaos Rising announcement",
        text("""
            UPDATE market_events SET
                event_date = '2026-03-12',
                description = 'Chaos Rising (Mega Evolution-Chaos Rising) set officially announced by Pokemon Company',
                source_url = 'https://www.pokemon.com/us/pokemon-news/the-pokemon-tcg-mega-evolution-chaos-rising-expansion-arrives-on-may-22-2026',
                expected_window_days = 30
            WHERE description LIKE '%Pokemon YouTuber coordinated box break%'
        """),
    ),
    # Event 4b: Chaos Rising release (new row — JSONB not PG ARRAY)
    (
        "Event 4b — Chaos Rising release INSERT",
        text("""
            INSERT INTO market_events (event_date, event_type, description, source_url, expected_window_days, affected_set_ids)
            VALUES (
                '2026-05-22',
                'RELEASE',
                'Chaos Rising worldwide release - 4th Mega Evolution set, chase cards: Mega Greninja ex SIR/MHR',
                'https://www.pokemon.com/us/pokemon-news/the-pokemon-tcg-mega-evolution-chaos-rising-expansion-arrives-on-may-22-2026',
                90,
                '["sv11"]'::jsonb
            )
            ON CONFLICT DO NOTHING
        """),
    ),
    # Event 5: Prismatic Evolutions correct launch date
    (
        "Event 5 — Prismatic Evolutions launch",
        text("""
            UPDATE market_events SET
                event_date = '2025-01-17',
                description = 'Prismatic Evolutions launch - mainstream media coverage of nationwide sellouts, ETB resale prices reach $250+',
                source_url = 'https://gocollect.com/blog/ready-for-the-release-of-pokemon-prismatic-evolutions'
            WHERE description LIKE '%Prismatic Evolutions Eevee%'
        """),
    ),
]

with engine.connect() as conn:
    for label, stmt in updates:
        result = conn.execute(stmt)
        affected = result.rowcount
        print(f"  {'OK' if affected > 0 else 'WARN(0 rows)'} {label}: {affected} row(s)")
        sys.stdout.flush()
    conn.commit()
    print("\nAll committed.")

    # Verify final state
    rows = conn.execute(text(
        "SELECT event_type, event_date::date, description FROM market_events ORDER BY event_date"
    )).fetchall()
    print(f"\nFinal market_events ({len(rows)} rows):")
    for r in rows:
        print(f"  {r[0]:12} {r[1]}  {r[2][:70]}")
