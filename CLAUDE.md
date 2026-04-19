# Flashcard Planet — Project Context for Claude Code

## Mission
We are migrating Flashcard Planet from a Pokemon-only TCG signal platform 
to a multi-TCG market intelligence platform. Target games (in order):
Pokemon (already live) → Yu-Gi-Oh → MTG → One Piece TCG → Lorcana.

## Architecture principles
1. Every new feature must be game-agnostic.
2. We respect third-party API terms, especially Scryfall's no-paywall clause.
3. Existing 138 tests must pass after every task.
4. Pokemon user experience must not degrade during the migration.

## Where to find strategy docs
- docs/strategy/00_index.md (navigation)
- docs/strategy/01_architecture_audit_tasks.md (17 Claude Code tasks)
- docs/strategy/02_cross_tcg_signal_design.md (schema + algorithm)
- docs/strategy/03_pricing_page_copy.md (Pro tier copy)
- docs/strategy/04_multi_tcg_pitch.md (external positioning)

## Key data models (current, pre-migration)
- Asset: the canonical card entity
- Observation: raw eBay/TCGplayer sale record
- PricePoint: aggregated daily price
- Signal: BREAKOUT/MOVE/WATCH/IDLE flag on an asset
- User.access_tier: "free" | "pro" | "trader"