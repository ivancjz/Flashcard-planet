# Pokemon Expansion Tier 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expand Pokemon TCG coverage from 15 sets / 2,674 cards to 25 sets / ~4,556 cards by adding 10 Tier 1 market-hot sets.

**Architecture:** (1) Add 8 new SetConfig entries to set_registry.py (sv2/sv3 already exist). (2) Introduce TIER1_BULK_SET_IDS constant covering all 14 sets for bulk-set-price-refresh. (3) Add --set-ids and --dry-run to import_pokemon_cards.py. (4) Create import_tier1_sets.py orchestrator.

**Tech Stack:** Python, SQLAlchemy, Pokemon TCG API v2, APScheduler

---

## Phase 0 — Verified Set IDs (2026-04-20)

All IDs confirmed against https://api.pokemontcg.io/v2/sets. User-predicted IDs were 100% correct.

| Set Name | API ID | Printed | Total (w/ secrets) | Release |
|---|---|---|---|---|
| Evolving Skies | swsh7 | 203 | 237 | 2021-08-27 |
| Lost Origin | swsh11 | 196 | 217 | 2022-09-09 |
| Crown Zenith | swsh12pt5 | 159 | 160 | 2023-01-20 |
| Silver Tempest | swsh12 | 195 | 215 | 2022-11-11 |
| Obsidian Flames | sv3 | 197 | 230 | 2023-08-11 |
| Paldea Evolved | sv2 | 193 | 279 | 2023-06-09 |
| Brilliant Stars | swsh9 | 172 | 186 | 2022-02-25 |
| Hidden Fates | sm115 | 68 | 69 | 2019-08-23 |
| Astral Radiance | swsh10 | 189 | 216 | 2022-05-27 |
| Shining Fates | swsh45 | 72 | 73 | 2021-02-19 |

**sv2 and sv3 already exist in SUPPORTED_SETS** — need only bulk-scope update, not new entries.

**Total new cards: 1,882** (237+217+160+215+230+279+186+69+216+73). Within target range.

**New P1_P2_BULK_SET_IDS (14 sets):**
`base1,base2,base3,base5,swsh7,swsh11,swsh12pt5,swsh12,sv3,sv2,swsh9,sm115,swsh10,swsh45`

---

## Task 1: Update set_registry.py — new SetConfig entries

**Files:**
- Modify: `backend/app/core/set_registry.py`

- [ ] Add 8 new SetConfig entries for swsh7, swsh11, swsh12pt5, swsh12, swsh9, sm115, swsh10, swsh45
- [ ] Add TIER1_BULK_SET_IDS constant covering all 14 sets
- [ ] Run tests: `python -m pytest --tb=short -q`
- [ ] Commit: `feat(coverage): add Tier 1 sets to set_registry and bulk scope`

---

## Task 2: Update config.py default

**Files:**
- Modify: `backend/app/core/config.py`

- [ ] Import TIER1_BULK_SET_IDS
- [ ] Set `pokemon_tcg_bulk_set_ids: str = TIER1_BULK_SET_IDS`
- [ ] Run tests: `python -m pytest --tb=short -q`
- [ ] Commit (squash into Task 1 commit)

---

## Task 3: Improve import_pokemon_cards.py

**Files:**
- Modify: `scripts/import_pokemon_cards.py`

Gaps to fill:
- `--set-ids` (comma-separated multi-set)
- `--dry-run` (no DB writes, count only)
- Progress print every 50 cards

- [ ] Add `--set-ids` to parse_args()
- [ ] Add `--dry-run` to parse_args()
- [ ] Add progress counter in main() loop
- [ ] Branch on dry-run in main(): skip flush_batch, accumulate counts
- [ ] Run tests: `python -m pytest --tb=short -q`
- [ ] Commit: `feat(import): add --set-ids, --dry-run, progress output`

---

## Task 4: Create orchestrator script

**Files:**
- Create: `scripts/import_tier1_sets.py`

- [ ] Write Python orchestrator that calls import_pokemon_cards per set with 30s sleep between
- [ ] Commit: `feat(import): add import_tier1_sets.py orchestrator`

---

## Task 5: Dry-run validation

- [ ] Run: `python scripts/import_pokemon_cards.py --set-id swsh45 --dry-run`
- [ ] Verify card count matches API (72-73 cards)
- [ ] No errors or None field warnings
- [ ] Commit: N/A (dry-run only)

---

## Deploy notes

- Merge only updates config and adds scripts — no DB writes
- Actual import requires manual `python scripts/import_tier1_sets.py`
- Rollback: revert PR; already-imported data stays in DB (orphaned but harmless)
