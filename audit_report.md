# TASK-000 — Pokemon-Specific Code Audit Report

**Generated:** 2026-04-19  
**Scope:** Production code only (`backend/`, `bot/`, `templates/`). Scripts in
`scripts/` excluded per CLAUDE.md §4.  
**Baseline:** 522 tests, all passing.

---

## Executive Summary

| Category | Count |
|---|---|
| Symbols that need renaming | **25** |
| Functions that need a `game` parameter | **8** |
| Interface abstraction points | **5** |

The `Asset` model has **no `game` field** — every query that filters by game
today uses `Asset.category == "Pokemon"`, a string literal scattered across 7
call-sites. That is the highest-priority structural blocker for multi-TCG.

---

## Category 1 — Files containing "pokemon"/"pkmn"/"ptcg" in their name

| File | Action |
|---|---|
| `backend/app/ingestion/pokemon_tcg.py` | Keep but extract interface (TASK-002); rename functions inside |
| `tests/test_pokemon_tcg_ingestion.py` | Rename → `test_tcg_provider_ingestion.py` after refactor |

> Note: All files in `scripts/` matching `*pokemon*` are excluded from this
> audit per CLAUDE.md §4 (historical one-offs).

---

## Category 2 — Class / function names containing "Pokemon"

### 2a. Classes

| Symbol | File | Line | Refactor direction |
|---|---|---|---|
| `PokemonCatalog` | `backend/app/ingestion/matcher/catalog.py` | 31 | Rename → `TcgCatalog`; extract `GameCatalog` ABC (TASK-002) |
| `TrackedPokemonPool` | `backend/app/core/tracked_pools.py` | 28 | Rename → `TrackedCardPool` (TASK-001) |

### 2b. Functions

| Symbol | File | Line | Refactor direction |
|---|---|---|---|
| `ingest_pokemon_tcg_cards()` | `backend/app/ingestion/pokemon_tcg.py` | 361 | Rename → `ingest_tcg_provider_cards()`; becomes impl of `GameDataClient` (TASK-002) |
| `get_catalog() -> PokemonCatalog` | `backend/app/ingestion/matcher/catalog.py` | 134 | Return type changes to `GameCatalog` (TASK-002) |
| `get_tracked_pokemon_pools()` | `backend/app/core/tracked_pools.py` | 38 | Rename → `get_tracked_card_pools(game)`; add `game` param (TASK-001) |
| `get_primary_smart_observation_pool()` | `backend/app/core/tracked_pools.py` | 91 | Returns `TrackedCardPool`; needs `game` param (TASK-001) |

### 2c. Constants

| Symbol | File | Line | Refactor direction |
|---|---|---|---|
| `POKEMON_CATEGORY` | `backend/app/ingestion/pipeline.py` | 50 | Remove; derive from `GAME_CONFIG[game].category` (TASK-001) |
| `_POKEMON_CATEGORY_ID` | `backend/app/ingestion/ebay/real_client.py` | 29 | Move into `GAME_CONFIG[Game.POKEMON].ebay_category_id` (TASK-006) |
| `POKEMON_TCG_PRICE_SOURCE` | `backend/app/core/price_sources.py` | 12 | Keep name (remains Pokemon-specific source); document as such |
| `PROVIDER_EXTERNAL_ID_PREFIX = "pokemontcg:"` | `backend/app/core/tracked_pools.py` | 7 | Move into `GAME_CONFIG[Game.POKEMON]`; per-game prefix (TASK-001) |

### 2d. Settings fields in `backend/app/core/config.py`

All 11 fields below are `pokemon_tcg_*` prefixed. They are wired into
`bulk_set_id_list` and scheduler paths. Keep them as-is for Pokemon
backward-compat, but future games get their own setting blocks via `GAME_CONFIG`
rather than new top-level `Settings` fields.

| Field | Line | Notes |
|---|---|---|
| `DEFAULT_POKEMON_TCG_CARD_IDS` | 11 | Keep; rename to `DEFAULT_POKEMON_CARD_IDS` in TASK-001 |
| `DEFAULT_POKEMON_TCG_TRIAL_CARD_IDS` | 13 | Keep |
| `DEFAULT_POKEMON_TCG_HIGH_ACTIVITY_TRIAL_CARD_IDS` | 22 | Keep |
| `DEFAULT_POKEMON_TCG_HIGH_ACTIVITY_V2_CARD_IDS` | 26 | Keep |
| `pokemon_tcg_api_base_url` | 59 | Move to `GAME_CONFIG` in TASK-002 |
| `pokemon_tcg_api_key` | 60 | Move to `GAME_CONFIG` in TASK-002 |
| `pokemon_tcg_card_ids` | 61 | Keep; generic `card_ids` per-game in TASK-001 |
| `pokemon_tcg_bulk_set_ids` | 62 | Keep; generic `bulk_set_ids` per-game in TASK-001 |
| `pokemon_tcg_trial_pool_label` | 63 | Keep |
| `pokemon_tcg_trial_card_ids` | 64 | Keep |
| `pokemon_tcg_high_activity_pool_label` | 65 | Keep |
| `pokemon_tcg_high_activity_card_ids` | 66 | Keep |
| `pokemon_tcg_high_activity_v2_pool_label` | 67 | Keep |
| `pokemon_tcg_high_activity_v2_card_ids` | 68 | Keep |
| `pokemon_tcg_schedule_enabled` | 105 | Superseded by `ingest_schedule_enabled`; already has compat shim |
| `pokemon_tcg_schedule_seconds` | 106 | Superseded by `ingest_interval_hours`; already has compat shim |

---

## Category 3 — Hardcoded Pokemon TCG API base URL

| File | Line | Snippet | Action |
|---|---|---|---|
| `backend/app/core/config.py` | 59 | `pokemon_tcg_api_base_url: str = "https://api.pokemontcg.io/v2"` | Move into `GAME_CONFIG[Game.POKEMON].external_api_base_url` (TASK-002) |
| `backend/app/ingestion/matcher/catalog.py` | 40 | `"https://api.pokemontcg.io/v2/cards?q=supertype:Pok%C3%A9mon&pageSize=250"` | This whole URL is Pokemon-specific; move into `PokemonGameDataClient` impl (TASK-002) |

---

## Category 4 — Hardcoded Pokemon set codes

### 4a. `backend/app/core/set_registry.py` (entire module is Pokemon-only)

The `SetConfig` dataclass and `SUPPORTED_SETS` list are conceptually correct but
Pokemon-scoped. No `game` field on `SetConfig`. All 16 sets are Pokémon TCG.

| Item | Lines | Action |
|---|---|---|
| `SetConfig` dataclass | 34–41 | Add `game: Game` field (TASK-001) |
| `SUPPORTED_SETS` list (16 entries) | 51–207 | Already the right pattern; each entry needs `game=Game.POKEMON` after TASK-001 |
| `P1_P2_SETS`, `P1_P2_CARD_IDS`, etc. | 218–230 | Rename to `POKEMON_P1_P2_SETS` etc. after `game` field added |
| Module docstring | 1–26 | Says "Pokémon TCG sets" — keep but note it will split per game |

### 4b. Hardcoded set IDs in tests and other files

| File | Lines | Codes | Action |
|---|---|---|---|
| `tests/test_set_registry.py` | 51–166 | `base1`, `base2`, `base3`, `base5`, `jungle`, `fossil` | Tests are correct for Pokemon; no change until TASK-001 adds `game` |
| `tests/test_backfill.py` | 46–97 | `base1-4`, `base1-6` | Test fixtures; no change needed now |
| `tests/test_gap_detector.py` | 27–59 | `base1`, `jungle` | Test fixtures; no change needed now |
| `tests/test_cards_enriched_api.py` | 36–55 | `base1-4` | Test fixture; no change needed now |
| `tests/test_asset_tagging.py` | 68–69 | `pokemontcg:base1-4:holofoil` | Fixture; will update after TASK-001 |

---

## Category 5 — Database fields / queries assuming Pokemon-only

### 5a. No `game` field on the `Asset` model

**File:** `backend/app/models/asset.py` — lines 15–60  

The `Asset` table has `category` (a free-text string, currently always
`"Pokemon"`) but no `game` field. Every cross-game query will be impossible
without adding this field.

**Resolution:** TASK-001 — add `game` column with `DEFAULT "pokemon"`, NOT NULL.
This is the **single most important structural change** in the entire migration.

### 5b. Call-sites filtering `Asset.category == "Pokemon"` hardcoded

These 7 call-sites will all need to become `.filter(Asset.game == game)` after
TASK-001.

| File | Line | Code fragment | Action |
|---|---|---|---|
| `backend/app/ingestion/pokemon_tcg.py` | 518 | `Asset.category == "Pokemon"` in `_query_missing_price` | Add `game` param to function (TASK-001) |
| `backend/app/ingestion/pokemon_tcg.py` | 550 | `Asset.category == "Pokemon"` in `_query_missing_image` | Add `game` param (TASK-001) |
| `backend/app/ingestion/pipeline.py` | 115, 301 | `category=POKEMON_CATEGORY` | Add `game` param to pipeline (TASK-006) |
| `backend/app/site.py` | 570 | `Asset.category == "Pokemon"` | Add game filter after TASK-001 |
| `backend/app/site.py` | 584 | `Asset.category == "Pokemon"` | Add game filter after TASK-001 |
| `backend/app/site.py` | 786 | `Asset.category == "Pokemon"` | Add game filter after TASK-001 |
| `backend/app/site.py` | 1007 | `Asset.category == "Pokemon"` | Add game filter after TASK-001 |
| `backend/app/site.py` | 1112 | `Asset.category == "Pokemon"` | Add game filter after TASK-001 |

### 5c. Pokemon-specific `external_id` prefix baked into logic

| File | Line | Code fragment | Action |
|---|---|---|---|
| `backend/app/ingestion/pokemon_tcg.py` | 212 | `f"pokemontcg:{card_id}:{price_field}"` | Move prefix to `GAME_CONFIG` (TASK-001) |
| `backend/app/core/tracked_pools.py` | 7 | `PROVIDER_EXTERNAL_ID_PREFIX = "pokemontcg:"` | Per-game config (TASK-001) |
| `backend/app/services/asset_tagging.py` | 172 | `external_id.startswith("pokemontcg:")` | Use game-aware prefix lookup (TASK-001) |

### 5d. AI mapper hardcodes `game = "Pokemon"` in LLM system prompt

**File:** `backend/app/ingestion/matcher/ai_mapper.py` — line 27  
```python
_SYSTEM_PROMPT = """...
- game is always "Pokemon" for this pipeline
...
```
**Resolution:** TASK-003 — parameterise prompt template by game.

---

## Interface Abstraction Points (for TASK-002 / TASK-003)

| # | Current shape | Needed abstraction | Task |
|---|---|---|---|
| 1 | `backend/app/ingestion/pokemon_tcg.py` (whole module) | `GameDataClient` ABC with `fetch_card_by_id`, `fetch_cards_by_set`, `list_sets`, `get_image_url` | TASK-002 |
| 2 | `PokemonCatalog` | `GameCatalog` ABC — generic in-memory card catalog per game | TASK-002 |
| 3 | `backend/app/core/set_registry.py` | Per-game set registries under a common `SetRegistry` lookup | TASK-001 |
| 4 | `backend/app/ingestion/matcher/ai_mapper.py` + `rule_engine.py` | `MappingRuleSet` ABC with `parse_title()`, `compute_match_confidence()` | TASK-003 |
| 5 | `backend/app/ingestion/ebay/real_client.py` (`_POKEMON_CATEGORY_ID`, search terms) | `GAME_CONFIG[game].ebay_category_id` + `ebay_search_terms` list | TASK-006 |

---

## Three Numbers (Summary)

| Metric | Count |
|---|---|
| **Symbols to rename** | **25** |
| **Functions needing a `game` parameter** | **8** |
| **Interface abstraction points** | **5** |

---

## Recommended Execution Order

1. **TASK-001** — Add `Game` enum + `game` column to `Asset`. Backfill all
   existing rows to `"pokemon"`. This unblocks all subsequent tasks.
2. **TASK-002** — Extract `GameDataClient` ABC; move `pokemon_tcg.py` to
   `PokemonGameDataClient`. Rename `PokemonCatalog`.
3. **TASK-003** — Extract `MappingRuleSet` ABC; move Pokemon rules to
   `PokemonMappingRules`. Parameterise `ai_mapper` system prompt.
4. **TASK-006** — Move `_POKEMON_CATEGORY_ID` and eBay search terms into
   `GAME_CONFIG`.
5. **TASK-007** — Add `game` filter to API endpoints; update `site.py` call-sites.

None of the 8 functions that need a `game` param require code logic changes —
they just need the param added and the hardcoded `"Pokemon"` string replaced with
`game.value`. The real structural work is TASK-001 (data model) and TASK-002
(client interface).

---

## What Is Already Game-Agnostic (No Changes Needed)

- `backend/app/services/signal_service.py` — no Pokemon references; game-neutral
- `backend/app/services/signal_explainer.py` — no Pokemon references; game-neutral
- `backend/app/services/price_service.py` — game-neutral
- `backend/app/services/permissions.py` — game-neutral
- `backend/app/models/` — all models except `Asset` are game-neutral
- `backend/app/core/data_service.py` — already a game-agnostic wrapper
- `backend/app/core/response_types.py` — game-neutral
- `bot/` — game-neutral (uses `DataService`)
