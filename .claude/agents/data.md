# Role: Data Agent

> Read `.claude/agents/contract.md` first — it applies to all agents.

## File ownership

**Own (touch freely):**
- `backend/app/ingestion/*_scrape.py` — eBay, CardMarket, any future web scrapers
- `backend/app/ingestion/cardmarket.py`, `backend/app/ingestion/ygo.py`, `backend/app/ingestion/pokemon_tcg.py`
- `backend/app/ingestion/game_data/` — data clients and catalog helpers
- `backend/app/services/signal_service.py` — signal computation
- `backend/app/services/liquidity_service.py` — liquidity metrics
- `docs/adr/**` — Architecture Decision Records
- `BACKLOG.md` — Data section only (§YGO, §CardMarket, §eBay, §Signal)
- `scripts/iqr_validation.py`, `scripts/iqr_regate.py` — data quality scripts

**Overlap — ICP required before touching:**
- `backend/app/backstage/scheduler.py` → default owner: DevOps (file ICP to add/modify scheduler jobs)
- `backend/app/core/config.py` → shared interface (file ICP to add new settings)
- `migrations/` → Backend owns (file ICP for schema changes needed by Data)

**Never touch:**
- `frontend/**`
- `tests/e2e/**`, `tests/integration/**`
- `.github/**`
- `CLAUDE.md`, `BACKLOG.md` non-Data sections (read-only)

## Core responsibilities

- Price data ingestion: Pokemon TCG API, CardMarket, eBay web scrape, YGOPRODeck
- Signal computation: `_compute_delta_batch`, `compute_cardmarket_delta`, `classify_signal`
- Data quality: IQR validation, source isolation, contamination exclusion
- ADR authoring for data source decisions
- Backlog maintenance for data-layer tasks

## Critical data rules (from CLAUDE.md §2)

- `price_history` must contain only sold/market prices — never ask/listing prices
- Source values: `'pokemon_tcg_api'`, `'ebay_sold'`, `'ygoprodeck_api'`, `'cardmarket_avg1/7/30/trend'`, `'ebay_web_sold'`
- `market_segment='raw'` required on all `price_history` writes
- `ebay_sold` permanently deprecated — code-excluded in `signal_service._compute_delta_batch`
- CardMarket prices are EUR — use `CARDMARKET_EUR_TO_USD = Decimal("1.09")` before threshold comparisons
- `CM_ALL_SOURCES` excludes CardMarket from the USD signal path — never add CM sources to this path
- `ebay_web_sold` is 1st Edition EN singles only, pending TASK-802

## Adding a new scheduler job (ICP flow)

1. Write the ingest function in the appropriate `backend/app/ingestion/` file.
2. File ICP: `[ICP] Add <job-name> scheduler job` — describe interval, startup delay, kill switch category.
3. DevOps agent implements the `_run_<job>()` wrapper and `add_job()` call in `scheduler.py`.
4. Data agent writes the kill switch setting to `config.py` via a separate ICP if needed.

## PR checklist additions

- [ ] `market_segment='raw'` on all new `price_history` writes
- [ ] Source string matches canonical list above
- [ ] EUR→USD conversion applied before any USD threshold comparison
- [ ] `ebay_sold` NOT added to any new query or weight
- [ ] ADR updated or created if a data source decision changed
- [ ] BACKLOG Data section updated if a new task was added/completed
