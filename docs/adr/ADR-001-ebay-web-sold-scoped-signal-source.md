# ADR-001: eBay Web Scrape as Scoped YGO Sold-Price Signal Source

**Date:** 2026-05-17  
**Status:** Accepted — pending dry-run IQR validation before production activation  
**Supersedes:** Partial reversal of the eBay sold-price deprecation (2026-05-14, CLAUDE.md §2)

---

## Context

The eBay Finding API was permanently decommissioned (~2025-02-05). The subsequent feasibility test of the eBay Browse API (ask prices) showed 90% grade-mix contamination and median IQR 189%/129%, making it unsuitable as a sold-price proxy for signal computation (CLAUDE.md §2).

At the same time, YGOPRODeck returns byte-identical prices on POTE/TOCH assets across 14+ days of polling — the YGO signal engine produces only IDLE/INSUFFICIENT_DATA on currently-seeded sets. CardMarket (EUR, daily avg) fills part of the gap, but USD-denominated real transaction data is still absent.

A feasibility probe on 2026-05-16 confirmed that eBay's public completed-listings pages serve real sold prices without authentication, with ~50–60 results per per-rarity card query. Rarity is already stored in `Asset.variant` for all YGO assets.

---

## Decision

Implement `ebay_web_sold` as a **scoped, opt-in, YGO-only** sold-price signal source using HTTP scraping of eBay's completed-listings pages. This is a partial reversal of the eBay deprecation, limited to the web scrape path only. The `ebay_sold` (Finding API) source remains permanently deprecated and code-excluded.

**Scope constraints (all enforced in code):**

| Constraint | Implementation |
|---|---|
| YGO assets only | `WHERE game = 'yugioh'` query filter |
| Per-rarity search | Query string: `"{name} {card_number} {variant} yugioh"` |
| EN singles only | `_filter_valid_singles`: drops JP/KR, graded (PSA/BGS/CGC/HGA), multi-qty, sealed |
| Price bounds | `PRICE_FLOOR_USD = $0.50`, `PRICE_CEILING_USD = $500.00` |
| Aggregated output | One median-price row per asset per run — not raw transactions |
| Per-run asset cap | `ebay_web_sold_max_assets_per_run = 250` (env-configurable) |
| Kill switch | `EBAY_WEB_SOLD_ENABLED = false` (Category β, default off) |
| Source isolation | `source = 'ebay_web_sold'`; excluded from `ebay_sold` code paths |

**Known limitations:**

- Condition mixing (NM vs LP) is unfiltered; median attenuates but does not eliminate
- Edition mixing (1st vs Unlimited) is unfiltered; same attenuation caveat
- Rarity isolation relies on eBay's keyword matching — not verified at title level
- Page-structure changes at eBay will silently reduce `assets_written` (detectable via `no_op` run status in `scheduler_run_log`)

**Signal engine integration:**

- `ebay_web_sold` is USD-denominated → enters `_compute_delta_batch` (standard path)
- Weight: `ebay_web_sold = 1.0` in `signal_delta_source_weights` default
- `market_segment = 'raw'` on all writes
- Not in `CM_ALL_SOURCES` (CardMarket EUR exclusion set)

---

## Activation gate

The kill switch (`EBAY_WEB_SOLD_ENABLED`) must remain `false` until:

1. **Dry-run IQR validation passes** (Step 3 of the eBay web scrape rollout plan): run `ingest_ebay_web_sold` against production DB with `max_assets=20`, inspect `scheduler_run_log.meta_json` and raw `price_history` rows, compute IQR per asset. Accept if median IQR < 100% on ≥50% of sampled assets. Reject if any asset shows a price that is clearly a wrong-rarity outlier (e.g., Starlight Rare price appearing in a Secret Rare asset's history).

2. **PR #65 merged** (zero-write runs marked `no_op`).

---

## Alternatives considered

| Alternative | Rejected reason |
|---|---|
| eBay Browse API (ask prices) | Q1 analysis: IQR 189%/129%, grade-mixed, ask ≠ sold |
| PriceCharting API | No public API; scrape complexity similar to eBay with lower volume |
| TCGPlayer YGO prices | Not evaluated; may require partnership; deferred |
| CardMarket only | Already live; EUR-only; no USD sold-price validation |

---

## Consequences

**Positive:** Real USD sold-price data for YGO assets; enables BREAKOUT/MOVE/WATCH on YGO if price movement exists; no API key or authentication required.

**Negative:** Web scraping is fragile to eBay page-structure changes; condition/edition mixing reduces signal precision vs. a structured API; no rate-limit guarantee from eBay.

**Monitoring:** `scheduler_run_log` `status=no_op` indicates zero EN singles found (expected during low-volume periods or eBay structure changes). `status=partial` indicates HTTP errors on some assets. `status=error` requires immediate investigation.
