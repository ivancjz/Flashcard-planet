"""
backend/app/core/set_registry.py  — B1

Canonical registry of Pokémon TCG sets supported by Flashcard Planet.

Usage
-----
Add a SetConfig entry here, then set the corresponding env variable
(or rely on the defaults) to include the set's cards in ingestion.

The scheduler reads:
  settings.pokemon_tcg_card_ids        — explicit card ID list (path A)
  settings.pokemon_tcg_bulk_set_ids    — set ID list for bulk refresh (path B)

This file provides the canonical set metadata and the default card-ID
ranges so both paths can be populated from one source of truth.

Adding a new set
----------------
1. Add a SetConfig to SUPPORTED_SETS.
2. Add its set_id to DEFAULT_BULK_SET_IDS.
3. If the set is small enough for path A, add its card IDs to
   DEFAULT_CARD_IDS (generated from set_id + card_count).
4. Run alembic upgrade head (no migration needed — just config).
5. The next scheduler tick will ingest the new cards.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SetConfig:
    set_id: str           # Pokemon TCG API set ID (e.g. "base1")
    name: str             # Human-readable name
    card_count: int       # Total cards in the set (for ID generation)
    release_year: int
    series: str           # e.g. "Base", "Jungle", "Neo", "EX"
    priority: int         # Lower = ingested first / more frequently
    notes: str = ""


# ── Phase 2B priority order (matches project plan B1) ────────────────────
#
# P1  Base Set         already in DEFAULT_POKEMON_TCG_CARD_IDS
# P2  Jungle, Fossil, Team Rocket
# P3  Modern high-activity sets (Scarlet & Violet)
# P4  Broader coverage

SUPPORTED_SETS: list[SetConfig] = [

    # ── P1: Base Set (already ingested) ──────────────────────────────────
    SetConfig(
        set_id="base1",
        name="Base Set",
        card_count=102,
        release_year=1999,
        series="Base",
        priority=1,
        notes="Core set. Already in DEFAULT_POKEMON_TCG_CARD_IDS.",
    ),

    # ── P2: Classic expansions ────────────────────────────────────────────
    SetConfig(
        set_id="base2",
        name="Jungle",
        card_count=64,
        release_year=1999,
        series="Base",
        priority=2,
        notes="P2 expansion — classic collectible demand.",
    ),
    SetConfig(
        set_id="base3",
        name="Fossil",
        card_count=62,
        release_year=1999,
        series="Base",
        priority=2,
        notes="P2 expansion — classic collectible demand.",
    ),
    SetConfig(
        set_id="base4",
        name="Base Set 2",
        card_count=130,
        release_year=2000,
        series="Base",
        priority=3,
        notes="Reprint set. Lower priority than original Base.",
    ),
    SetConfig(
        set_id="base5",
        name="Team Rocket",
        card_count=83,
        release_year=2000,
        series="Base",
        priority=2,
        notes="P2 expansion — Dark cards, strong collector interest.",
    ),

    # ── Gym series ────────────────────────────────────────────────────────
    SetConfig(
        set_id="gym1",
        name="Gym Heroes",
        card_count=132,
        release_year=2000,
        series="Gym",
        priority=3,
    ),
    SetConfig(
        set_id="gym2",
        name="Gym Challenge",
        card_count=132,
        release_year=2000,
        series="Gym",
        priority=3,
    ),

    # ── Neo series ────────────────────────────────────────────────────────
    SetConfig(
        set_id="neo1",
        name="Neo Genesis",
        card_count=111,
        release_year=2000,
        series="Neo",
        priority=3,
        notes="Lugia, Typhlosion — strong collector demand.",
    ),
    SetConfig(
        set_id="neo2",
        name="Neo Discovery",
        card_count=75,
        release_year=2001,
        series="Neo",
        priority=4,
    ),
    SetConfig(
        set_id="neo3",
        name="Neo Revelation",
        card_count=66,
        release_year=2001,
        series="Neo",
        priority=4,
    ),
    SetConfig(
        set_id="neo4",
        name="Neo Destiny",
        card_count=113,
        release_year=2002,
        series="Neo",
        priority=4,
    ),

    # ── Sword & Shield — Tier 1 market-hot sets ──────────────────────────
    SetConfig(
        set_id="swsh7",
        name="Evolving Skies",
        card_count=203,
        release_year=2021,
        series="Sword & Shield",
        priority=3,
        notes="Tier 1 — Umbreon/Rayquaza VMAX, very high collector demand.",
    ),
    SetConfig(
        set_id="swsh9",
        name="Brilliant Stars",
        card_count=172,
        release_year=2022,
        series="Sword & Shield",
        priority=3,
        notes="Tier 1 — Charizard VSTAR, first VSTAR set.",
    ),
    SetConfig(
        set_id="swsh10",
        name="Astral Radiance",
        card_count=189,
        release_year=2022,
        series="Sword & Shield",
        priority=3,
        notes="Tier 1 — Origin Forme Palkia/Dialga VSTAR.",
    ),
    SetConfig(
        set_id="swsh11",
        name="Lost Origin",
        card_count=196,
        release_year=2022,
        series="Sword & Shield",
        priority=3,
        notes="Tier 1 — Giratina VSTAR, Lost Zone mechanic reintroduction.",
    ),
    SetConfig(
        set_id="swsh12",
        name="Silver Tempest",
        card_count=195,
        release_year=2022,
        series="Sword & Shield",
        priority=3,
        notes="Tier 1 — Lugia VSTAR, high finance activity.",
    ),
    SetConfig(
        set_id="swsh12pt5",
        name="Crown Zenith",
        card_count=159,
        release_year=2023,
        series="Sword & Shield",
        priority=3,
        notes="Tier 1 — Galarian Gallery subset, Regieleki/Regidrago VSTAR.",
    ),

    # ── Sun & Moon — Tier 1 market-hot sets ──────────────────────────────
    SetConfig(
        set_id="sm115",
        name="Hidden Fates",
        card_count=68,
        release_year=2019,
        series="Sun & Moon",
        priority=3,
        notes="Tier 1 — Shiny Vault subset, extremely high collector demand.",
    ),

    # ── Sword & Shield Subsets ────────────────────────────────────────────
    SetConfig(
        set_id="swsh45",
        name="Shining Fates",
        card_count=72,
        release_year=2021,
        series="Sword & Shield",
        priority=3,
        notes="Tier 1 — Shiny Vault subset, Charizard VMAX.",
    ),

    # ── P3: Modern high-activity ──────────────────────────────────────────
    SetConfig(
        set_id="sv1",
        name="Scarlet & Violet Base Set",
        card_count=198,
        release_year=2023,
        series="Scarlet & Violet",
        priority=3,
        notes="P3 — high secondary market activity.",
    ),
    SetConfig(
        set_id="sv2",
        name="Paldea Evolved",
        card_count=193,
        release_year=2023,
        series="Scarlet & Violet",
        priority=3,
    ),
    SetConfig(
        set_id="sv3",
        name="Obsidian Flames",
        card_count=197,
        release_year=2023,
        series="Scarlet & Violet",
        priority=3,
        notes="Charizard ex — high demand.",
    ),
    SetConfig(
        set_id="sv3pt5",
        name="151",
        card_count=207,
        release_year=2023,
        series="Scarlet & Violet",
        priority=3,
        notes="Original 151 Pokémon reprint — very high demand.",
    ),
    SetConfig(
        set_id="sv4",
        name="Paradox Rift",
        card_count=182,
        release_year=2023,
        series="Scarlet & Violet",
        priority=3,
    ),
    SetConfig(
        set_id="sv4pt5",
        name="Paldean Fates",
        card_count=245,
        release_year=2024,
        series="Scarlet & Violet",
        priority=3,
    ),
]


# ── Derived constants for config.py defaults ──────────────────────────────

def _card_ids_for_set(set_id: str, card_count: int) -> list[str]:
    """Generate card IDs in format 'setId-N' for N in 1..card_count."""
    return [f"{set_id}-{n}" for n in range(1, card_count + 1)]


# P1 + P2 sets — used as DEFAULT_POKEMON_TCG_CARD_IDS in config.py
P1_P2_SETS: list[SetConfig] = [s for s in SUPPORTED_SETS if s.priority <= 2]

P1_P2_CARD_IDS: list[str] = [
    card_id
    for s in P1_P2_SETS
    for card_id in _card_ids_for_set(s.set_id, s.card_count)
]

# All sets — used as DEFAULT_BULK_SET_IDS in config.py
ALL_BULK_SET_IDS: str = ",".join(s.set_id for s in SUPPORTED_SETS)

# P1+P2 only bulk IDs (conservative default)
P1_P2_BULK_SET_IDS: str = ",".join(s.set_id for s in P1_P2_SETS)

# Tier 1 expansion — all sets currently tracked in production (2026-04-25).
# Covers all sets in the DB; ensures bulk refresh runs even without env var override.
TIER1_BULK_SET_IDS: str = ",".join([
    # P1/P2 classics
    "base1", "base2", "base3", "base5",
    # Sword & Shield Tier 1
    "swsh7", "swsh9", "swsh10", "swsh11", "swsh12", "swsh12pt5", "swsh45",
    # Sun & Moon Tier 1
    "sm115",
    # Scarlet & Violet — in SUPPORTED_SETS
    "sv2", "sv3", "sv3pt5",
    # Scarlet & Violet — tracked in production (not yet in SUPPORTED_SETS)
    "sv8pt5", "sv8", "sv9", "sv10",
    # Japanese Scarlet & Violet sets tracked in production
    "rsv10pt5", "zsv10pt5", "me1", "me2", "me2pt5", "me3",
])


# ── Lookup helpers ────────────────────────────────────────────────────────

_SET_BY_ID: dict[str, SetConfig] = {s.set_id: s for s in SUPPORTED_SETS}


def get_set(set_id: str) -> SetConfig | None:
    return _SET_BY_ID.get(set_id)


def sets_by_priority(max_priority: int = 4) -> list[SetConfig]:
    return sorted(
        [s for s in SUPPORTED_SETS if s.priority <= max_priority],
        key=lambda s: (s.priority, s.release_year),
    )
