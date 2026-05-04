# One Piece TCG Integration — Research Spike

**Status:** Research complete — awaiting operator go/no-go decision
**Task:** TASK-202
**Date:** 2026-05-04
**Author:** Claude Code
**Operator decision required:** §4 (go/no-go), §5 (source choice), §6 (first sets)

---

## TL;DR

One Piece TCG is a viable third game. Secondary market is larger than YGO by monthly volume (#3 on TCGPlayer in Q4 2025). Data infrastructure is weaker than Pokémon/YGO — no official API exists; pricing comes from TCGPlayer-proxy third parties. Cost estimate: **$50/mo** for production-grade pricing (tcgapi.dev Pro tier) + negligible eBay Browse API usage (existing budget). Implementation effort comparable to YGO Phase 1.

---

## 1. Data source options

### 1a. Official Bandai

**Not available.** `en.onepiece-cardgame.com/cardlist/` is HTML-only, no developer API, no structured export. Bandai has no developer program. All third-party OPTCG data sources ultimately scrape Bandai's site.

Contrast: YGO has YGOPRODeck (free, unofficial but stable API); Pokémon has pokemon-tcg.io (unofficial but actively maintained). One Piece has nothing comparable from the primary party.

### 1b. optcgapi.com (community REST API)

- **Type:** Free REST API, hobby project. Daily scraper.
- **Coverage:** OP01–OP12, Extra Boosters EB01/EB02, Premium Boosters PRB01/PRB02, starter decks ST01–ST28, 900+ promos.
- **Pricing data:** Yes — sourced from TCGPlayer. **14-day rolling history only.**
- **Catalog data:** Yes — card name, type, color, rarity, set, card text.
- **Rate limits:** Published only as "some limits per day" — no number. Contact via Discord.
- **ToS:** None published. Non-commercial hobby project; operator community norm assumes non-commercial use.
- **SLA:** None. One-person project.

**Verdict:** Best free option for prototyping Phase 1. Too fragile for a paying-user production dependency. 14-day history means we'd need to accumulate our own longitudinal price history from day one (same pattern as YGO).

### 1c. tcgapi.dev (TCGPlayer proxy — paid)

- **Type:** Commercial REST API. Mirrors TCGPlayer pricing daily.
- **Coverage:** 6,643 One Piece cards across 73 sets. Updated daily.
- **Pricing data:** Market price, low price, foil price, 24h/7d/30d change. Price history from March 2025.
- **Rate limits by tier:**
  - Free: 100 req/day, non-commercial only
  - **Pro: $49.99/mo, 10,000 req/day, full price history, commercial license**
  - Business: $99.99/mo, 50,000 req/day
- **Risk:** Not TCGPlayer itself. If TCGPlayer enforces ToS, this proxy goes dark. No historical precedent for this happening to similar proxies.

**Verdict:** Best production-grade pricing source. $49.99/mo is the cost of treating OPTCG pricing seriously.

### 1d. JustTCG (justtcg.com)

- **Type:** Commercial REST API. TCGPlayer proxy with deeper statistical endpoints.
- **Coverage:** One Piece supported.
- **Pricing data:** Current price, 24h/7d/30d % changes, historical (7/30/90/180/365d), min/max, standard deviation, trend slopes.
- **Tiers:** Free (100 req/day), Starter, Professional (5,000 req/day), Enterprise.
- **Advantage over tcgapi.dev:** Richer statistics — standard deviation and trend slope endpoints would feed directly into our signal algorithm.

**Verdict:** Alternative to tcgapi.dev worth evaluating if the signal team wants pre-computed volatility metrics. Likely similar pricing. No confirmed cost captured during research.

### 1e. eBay Browse API (active listings)

**Note on current platform state:** The eBay Finding API (`findCompletedItems`) was decommissioned 2025-02-05. Our existing `ebay_sold.py` already handles this gracefully — it tries Finding API first (returns `None` when it fails) and falls through to Browse API automatically. The code's Browse API path has been the de facto live path since February 2025. This is relevant for OPTCG: we can extend the same Browse API integration to One Piece without any new eBay infrastructure.

- **Data type:** Active listings (not sold prices). Price is "current asking," not "last transaction."
- **Coverage:** One Piece cards are listed on eBay. Category ID for OPTCG singles TBD (need to determine eBay category ID during implementation).
- **Cost:** Existing eBay developer account. No incremental cost.
- **Search terms for OPTCG:** `"One Piece" <card name> <set code>` + filter out sealed product.

**Verdict:** Use as secondary price source for market breadth, consistent with Pokémon/YGO approach. Data quality same as current YGO eBay data — active listings, not sold. The `market_segment='raw'` filter pattern from PR #26 applies here too.

### 1f. Limitlesstcg (onepiece.limitlesstcg.com)

- **Type:** Website with card database and tournament results. **No API.**
- **Pricing:** Affiliate redirect links to TCGPlayer/Cardmarket only. Not machine-readable.

**Verdict:** Useful for set metadata and tournament context; not a price source.

### 1g. punk-records / vegapull (GitHub)

- **punk-records** (`github.com/buhbbl/punk-records`): Static versioned JSON of Bandai card data, 7 languages (EN, JP, ZH, FR, TH). No pricing. Card name, type, color, cost, power, counter, text.
- **vegapull** (`github.com/Coko7/vegapull`): Rust CLI that scrapes Bandai's official site to produce the punk-records data.

**Verdict:** Best free catalog source if optcgapi.com is down or rate-limited. No pricing, so would need to pair with tcgapi.dev.

---

## 2. Recommended architecture

**Phase 1 (prototype, pre-paying OPTCG users):**
- Catalog: `optcgapi.com` — free, covers OP01–OP12. Accept the no-SLA risk for phase 1.
- Pricing: `optcgapi.com` TCGPlayer prices as primary; eBay Browse API as secondary.
- Cost: $0/mo (within existing eBay budget).

**Phase 2 (production, any paying users relying on OPTCG data):**
- Catalog: `tcgapi.dev` Pro — $49.99/mo, covers all 73 sets, commercial license.
- Pricing: `tcgapi.dev` daily market price + historical.
- eBay Browse API: secondary source (active listings), no additional cost.
- Cost: $49.99/mo incremental.

**Why not eBay sold prices as primary?** The Finding API is decommissioned. Marketplace Insights API requires Business approval (not applied for). Browse API gives active listings — lower quality than actual sold prices. TCGPlayer proxy (tcgapi.dev) gives better signal for OPTCG, which has deep TCGPlayer market activity.

**Risk table:**

| Source | Reliability | Cost | Data quality | Commercial safe |
|---|---|---|---|---|
| optcgapi.com | Low (no SLA, 1 person) | Free | TCGPlayer prices, 14-day history | Unknown |
| tcgapi.dev Pro | Medium (not TCGPlayer itself) | $49.99/mo | TCGPlayer prices, full history | Yes |
| JustTCG Pro | Medium | ~$49/mo (est.) | TCGPlayer + stats | Yes |
| eBay Browse API | High | Free | Active listings only | Yes |
| Bandai official | N/A — no API | — | — | — |

---

## 3. Asset model mapping

One Piece cards fit the existing `Asset` 10-column unique constraint cleanly.

| Asset column | One Piece value |
|---|---|
| `asset_class` | `"TCG"` |
| `game` | `"onepiece"` |
| `name` | Card name, e.g. `"Monkey D. Luffy"` |
| `set_name` | Set name, e.g. `"Romance Dawn"` |
| `card_number` | Set card number, e.g. `"OP01-060"` |
| `year` | Release year, e.g. `2022` |
| `language` | `"EN"` for English prints; `"JP"` if tracking JP exclusives |
| `variant` | Rarity/finish descriptor (see below) |
| `grade_company` | `None` (raw cards only in Phase 1) |
| `grade_score` | `None` |

**Variant values** (key for OPTCG investment tracking — variant drives most price differences):

| Variant string | Description |
|---|---|
| `"Common"` | C rarity |
| `"Uncommon"` | UC rarity |
| `"Rare"` | R rarity |
| `"Super Rare"` | SR rarity |
| `"Secret Rare"` | SEC rarity, ~1 per 24 packs |
| `"Treasure Rare"` | TR, high-end insert |
| `"Alternate Art"` | Star (★) alternate art, rainbow holofoil |
| `"Manga Rare"` | Full manga panel art, foil textured, ~1 per 50–70 boxes — highest value per card |
| `"Golden Manga Rare"` | Gold foil variant, introduced OP-09 |
| `"Red Manga Rare"` | Red foil variant, introduced OP-13 |
| `"Leader"` | Leader card L rarity |
| `"Parallel Leader"` | Foil Leader variant |

**Price source values** (for `PriceHistory.source`):

| Source | `source` string |
|---|---|
| optcgapi.com | `"optcgapi"` |
| tcgapi.dev | `"tcgapi_dev"` |
| eBay Browse API | `"ebay_sold"` (existing source, same as YGO/Pokémon) |

**`market_segment`:** All Phase 1 raw cards → `"raw"`. Graded cards deferred to Phase 2+ (same pattern as existing YGO graded-shadow admission spec).

---

## 4. First 5 sets to seed

Rationale: maximize investable card count and price signal depth in first deployment.

| Priority | Set code | Set name | Release | Why |
|---|---|---|---|---|
| 1 | OP-01 | Romance Dawn | Dec 2022 | First set; vintage status; SEC/SR cards have established price history |
| 2 | OP-05 | Awakening of the New Era | 2023 | High secondary market liquidity; confirmed in multiple market analyses |
| 3 | OP-08 | Two Legends | Sep 2024 | First Golden Manga Rare in wide print; drove collector demand spike |
| 4 | OP-09 | Emperors of the New World | late 2024 | Gol D. Roger Manga Rare; highest single-card values in set |
| 5 | OP-13 | Carrying On His Will | Nov 2025 | Drove Q4 2025 volume surge; most active recent market |

**Not recommended for Phase 1:**
- Starter decks ST-01 to ST-28: structurally lower investment appeal (fixed contents, no chase rarity pull rates).
- Extra Boosters (EB-01/02), Premium Boosters (PRB-01/02): consider for Phase 2 alongside YGO expansion.
- OP-10 through OP-12: liquid but recent; wait to confirm price stability before adding to signal baseline.

---

## 5. Estimated cost

| Item | Phase 1 | Phase 2 |
|---|---|---|
| Card catalog / pricing API | $0 (optcgapi.com) | $49.99/mo (tcgapi.dev Pro) |
| eBay API budget | Within existing allocation | Within existing allocation |
| Infrastructure (compute, DB) | Negligible — 5 sets × ~100–200 cards × daily price points is <$0.50/mo on current Railway plan | Same |
| **Total incremental** | **$0/mo** | **~$50/mo** |

DB storage projection at Phase 1 launch (5 sets, ~150 unique cards, daily price points): ~150 rows/day from tcgapi pricing × 365 days = ~55k `price_history` rows/year. Negligible vs current ~800k+ rows on Postgres.

---

## 6. Open questions for operator

1. **Go / no-go on OPTCG?** Resource ask: 1 sprint of implementation work (Phase 1 = comparable to YGO Phase 1 PR #15). Revenue uplift: differentiation on OPTCG users. Risk: data source fragility higher than Pokémon/YGO.

2. **Source selection:** optcgapi.com free (Phase 1 only) → tcgapi.dev Pro ($49.99/mo) at Phase 2, or pay from day one?

3. **Language scope:** English only first, or should JP-exclusive Manga Rares (often priced 2–5× EN equivalents) be tracked from Phase 1?

4. **Precondition gating:** TASK-202 lists "TASK-201 not blocked" as precondition. TASK-201 (YGO expansion to 30 sets) itself requires TASK-101 (YGO signal graduation verification). If TASK-101 passes by 2026-05-07, TASK-201 can start, and OPTCG could follow. Should OPTCG wait for YGO signal health confirmation, or run in parallel?

---

## 7. Implementation notes (for when operator approves)

These are not decisions — just observations to inform the implementation PR scope.

- **Ingest pattern to follow:** Two-pass approach per Lesson 6 (catalog-price decoupling). Pass 1 creates `Asset` rows regardless of price availability. Pass 2 writes `price_history`. This avoids the YGO "13-set zero-asset" failure mode.
- **Set code format:** OP-XX (with hyphen) in official materials; source APIs may vary (OP01 vs OP-01). Normalize to `card_number = "OP01-060"` format (set code without hyphen, hyphen before card number).
- **No cron triggers** — interval trigger + `_STARTUP_DELAY` entry, consistent with all other scheduler jobs.
- **YGO code is the reference:** `backend/app/ingestion/ygo.py` + `backend/app/ingestion/game_data/yugioh_client.py`. One Piece client follows the same interface.
- **eBay category ID for OPTCG:** Needs to be looked up during implementation (not researched here). Add to `GAME_CONFIG` in `backend/app/models/game.py`.
- **NULL census gate:** Before enabling any signal filter that touches OPTCG rows, run the NULL census per CLAUDE.md §3.
