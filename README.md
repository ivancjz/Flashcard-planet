# Flashcard Planet

Flashcard Planet is a real-time card market intelligence MVP for trading cards and collectibles. This repository intentionally starts as a clean Python monolith: FastAPI for the backend API, PostgreSQL for persistence, and `discord.py` for the first bot interface.

## What is included

- FastAPI backend with a working price search endpoint and watchlist endpoints.
- PostgreSQL-ready SQLAlchemy models for `assets`, `price_history`, `users`, `watchlists`, and `alerts`.
- Universal asset model that can support Pokemon, sports cards, and future categories in the same schema.
- Discord bot with slash commands for `/price`, `/history`, `/predict`, `/topvalue`, `/topmovers`, `/watch`, `/watchlist`, `/unwatch`, and `/alerts`.
- APScheduler-based ingestion and alert evaluation loop for automatic Discord DM notifications.
- Seed data script with a few cross-category sample assets.
- First real ingestion pipeline using the Pokemon TCG API for a curated fixed set of Pokemon cards, now expanded to all Base Set Pokemon cards.
- Docker Compose for local PostgreSQL.

## Repository structure

```text
backend/
  app/
bot/
database/
scripts/
docs/
```

## Data model decisions

The `assets` table is category-agnostic. Instead of a Pokemon-specific schema, it stores the shared identity fields that are useful across TCG and sports cards:

- `asset_class`
- `category`
- `name`
- `set_name`
- `card_number`
- `year`
- `language`
- `variant`
- `grade_company`
- `grade_score`

`price_history` stores point-in-time price snapshots so future features like movers, charts, and alert evaluation can be built on top of historical data instead of overwriting a single value.

## Local setup

### 1. Create and activate a virtual environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure environment variables

```powershell
Copy-Item .env.example .env
```

Update `.env` if your PostgreSQL credentials or Discord values differ.

If your local `.env` already sets `POKEMON_TCG_CARD_IDS`, that local override will take precedence over the in-code default card list.

### 4. Start PostgreSQL

If you have Docker available:

```powershell
docker compose up -d postgres
```

### 5. Initialize the schema and ingest real Pokemon prices

```powershell
python -m scripts.init_db
python -m scripts.ingest_pokemon_tcg
```

`scripts.ingest_pokemon_tcg` deletes any old `sample_seed` rows from `price_history`, then fetches real prices for the card IDs in `POKEMON_TCG_CARD_IDS`.

If you still want demo-only data for development experiments, you can run:

```powershell
python -m scripts.seed_data
```

### 6. Run the API

```powershell
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) for Swagger UI.

### 7. Run the Discord bot

```powershell
python -m bot.main
```

If `DISCORD_GUILD_ID` is set, slash commands sync to that guild for faster iteration. If left blank, commands sync globally.

## Developer notes

For alert behavior, rearm rules, manual demo commands, cleanup commands, and test commands, see [docs/DEV_NOTES.md](C:\Flashcard-planet\docs\DEV_NOTES.md).

## First working API routes

- `GET /health`
- `GET /api/v1/prices/search?name=pikachu`
- `GET /api/v1/prices/history?name=charizard&limit=5`
- `GET /api/v1/prices/predict?name=charizard`
- `GET /api/v1/prices/topvalue?limit=5`
- `GET /api/v1/prices/topmovers`
- `POST /api/v1/watchlists`
- `GET /api/v1/watchlists/{discord_user_id}`
- `DELETE /api/v1/watchlists?discord_user_id=123&asset_name=Pikachu`
- `GET /api/v1/alerts/{discord_user_id}`

### Example watch payload

```json
{
  "discord_user_id": "1234567890",
  "asset_name": "Pikachu",
  "threshold_up_percent": 10,
  "threshold_down_percent": 5,
  "target_price": 11.5,
  "predict_signal_change": true,
  "predict_up_probability_above": 60,
  "predict_down_probability_above": 60
}
```

## Current MVP limitations

- Only one live market data source is integrated so far: Pokemon TCG API for a fixed list of Pokemon card IDs.
- No migrations yet; schema creation is done with `create_all()` for MVP speed.
- No authentication or admin flows yet.
- Alert delivery is Discord-DM-only for now; there is no alert history UI.
- Prediction alerts are heuristic and depend on limited recent history depth.

## Next practical steps

1. Add Alembic migrations before schema changes become frequent.
2. Expand real ingestion beyond the initial Pokemon TCG source and fixed card list.
3. Add alert history and richer watchlist management once the current alert loop is stable.
4. Improve asset search with better matching, filtering, and aliases.
5. Add basic tests for services and routes.

## Real price ingestion

### Chosen source

The first real source is the [Pokemon TCG API](https://docs.pokemontcg.io/). It is a practical MVP fit because:

- it has a simple HTTPS API with no scraping required
- it exposes TCGplayer-backed pricing data in the card payload
- it works well for a narrow Pokemon-only first pass
- it supports optional API keys, so local development stays easy

User-facing price reads, movers, predictions, and alerts are scoped to one active source at a time. For now, that active source is `pokemon_tcg_api`, and it is controlled by `PRIMARY_PRICE_SOURCE` in `.env`.

Provider wiring is now slot-based so a second provider can be added beside the first one later without another ingestion refactor:

- `PROVIDER_1_SOURCE=pokemon_tcg_api`
- `PROVIDER_2_SOURCE=` left blank until provider #2 exists
- `PRIMARY_PRICE_SOURCE` still decides which source powers `/price`, `/history`, `/predict`, `/topmovers`, and alerts

### Tracked pools

Flashcard Planet now tracks three Pokemon pools inside the same provider:

- `Base Set` for the classic layer
- `Scarlet & Violet 151 Trial` for the activity-focused test pool
- `High-Activity Trial` for a premium-rarity modern test pool

The pool split is driven by card-id lists, not by a new schema. That keeps the current Base Set flow unchanged and makes it easy to compare coverage and movement across all three groups.

`High-Activity Trial` is intentionally rule-based but still config-safe: it targets `sv8pt5-148` through `sv8pt5-180`, the premium top-end slice of Prismatic Evolutions. That keeps the experiment inside the current explicit-card-id ingestion model instead of adding a broader discovery layer before the provider itself is proven.

When a second provider is added later, keep it writing provider-tagged `price_history.source` rows beside the current source instead of merging histories immediately. That makes it easy to compare providers without mixing their cadence or semantics.

The scheduler and diagnostics are now prepared for that shape already:

- ingestion is routed through a small provider registry
- diagnostics can emit provider-scoped pool snapshots in addition to the current active-provider report
- once provider #2 exists, the summary script can compare the same pools across providers with minimal extra code

### Manual ingestion command

```powershell
python -m scripts.ingest_pokemon_tcg
```

To force just the trial pool on demand:

```powershell
python -m scripts.ingest_pokemon_tcg_trial
```

To force just the High-Activity Trial pool on demand:

```powershell
python -m scripts.ingest_pokemon_tcg_high_activity_trial
```

### Price history summary helper

To inspect whether repeated runs are actually building useful history over time:

```powershell
python -m scripts.price_history_summary
```

It prints:

- data-health totals and low-coverage counts
- row totals by source
- per-asset history counts for the active primary source
- first and latest captured timestamps
- the most recent price rows for the active primary source

The data-health section includes:

- tracked Pokemon-provider assets only
- total assets
- assets with real non-sample history
- average real history points per asset
- assets with fewer than 3, 5, and 8 real points
- recent real price rows added in the last 24 hours
- assets with at least one price change in the last 24 hours and 7 days
- percentage of recent comparable rows that actually changed price
- assets with no observed movement across full real history
- assets whose latest two real prices are unchanged

### Legacy tracked-asset cleanup helper

If you have old Pokemon rows from an earlier curated list, preview them with:

```powershell
python -m scripts.cleanup_legacy_pokemon_assets
```

To delete only legacy Pokemon assets that are outside the current `POKEMON_TCG_CARD_IDS` list and have no watchlists or alerts:

```powershell
python -m scripts.cleanup_legacy_pokemon_assets --apply
```

### Optional API key

`POKEMON_TCG_API_KEY` is optional. Without it, the Pokemon TCG API still works with lower public rate limits. If you have a key, place it in `.env`.

### Later scheduling

The backend scheduler now runs the same ingestion job automatically when the backend starts. By default it runs immediately on startup and then every hour.

You can configure it with:

```env
POKEMON_TCG_SCHEDULE_ENABLED=true
POKEMON_TCG_SCHEDULE_SECONDS=3600
```

To disable automatic background ingestion:

```env
POKEMON_TCG_SCHEDULE_ENABLED=false
```

### Fast local scheduler testing

For quick local verification, temporarily use:

```env
POKEMON_TCG_SCHEDULE_ENABLED=true
POKEMON_TCG_SCHEDULE_SECONDS=300
```

Then:

1. Restart the backend
2. Watch logs for the immediate startup run and the next repeated run
3. Run `python -m scripts.price_history_summary`
4. Test `/price` and `/topmovers` in Discord

When you are done, set `POKEMON_TCG_SCHEDULE_SECONDS=3600` again for the normal hourly interval.

### Comparing tracked pools

The data-health summary and scheduler logs now print separate sections for:

- `Base Set`
- `Scarlet & Violet 151 Trial`
- `High-Activity Trial`

Use this to compare after a few days:

1. Keep the scheduler running
2. Run `python -m scripts.price_history_summary`
3. Compare all three pool sections for:
   - assets with real history
   - average history depth
   - assets with price changes in the last 24h and 7d
   - percent of comparable rows that actually changed price
   - assets with no movement across full history
   - assets whose latest two prices are unchanged
4. Read the `Operator conclusion` block:
   - `expand smarter with current provider`
   - `keep testing current provider before deciding on provider #2`
   - `prepare second provider`

### Measuring whether data depth is improving

The simplest way to track progress over time is:

1. Keep scheduled ingestion running
2. Run `python -m scripts.price_history_summary` periodically
3. Compare these metrics over time:
   - `assets_with_real_history`
   - `average_real_history_points_per_asset`
   - `assets_with_fewer_than_3_real_points`
   - `assets_with_fewer_than_5_real_points`
   - `assets_with_fewer_than_8_real_points`
   - `recent_real_price_rows_last_24h`
   - `assets_with_price_change_last_24h`
   - `assets_with_price_change_last_7d`
   - `percent_recent_rows_changed_last_24h`
   - `percent_recent_rows_changed_last_7d`
   - `assets_with_no_price_movement_full_history`
   - `assets_with_unchanged_latest_price`

As coverage improves, you should generally see:

- more assets with real history
- a higher average history-point count
- fewer assets below the 3 / 5 / 8 point thresholds
- more recent real rows per 24 hours

## Alerts and demo workflow

The scheduler now evaluates alerts automatically after each ingestion run.

- Price movement alerts compare the latest real price against the previous real price point
- Rearmable alerts fire once, then wait to re-arm until the condition moves back inside range
- Prediction signal alerts fire only when the model label changes
- Prediction probability alerts fire when the configured probability crosses above the threshold, then re-arm after dropping back below it
- Target alerts remain one-shot and deactivate after firing

To preview a demo trigger without saving any test rows:

```powershell
python -m scripts.demo_alert_trigger --asset-name Charizard --percent-change 10
```

To commit a demo row so the running scheduler can act on it:

```powershell
python -m scripts.demo_alert_trigger --asset-name Charizard --percent-change 10 --commit
```

To clean up committed demo rows:

```powershell
python -m scripts.demo_alert_trigger --asset-name Charizard --cleanup
```

To run the basic automated alert tests:

```powershell
python -m unittest discover -s tests -v
```

### Verifying the API uses real data

1. Run `python -m scripts.ingest_pokemon_tcg`
2. Check a real ingested card:

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/prices/search?name=Pikachu"
```

The returned `source` should be `pokemon_tcg_api`, not `sample_seed`.

3. Check movers:

```powershell
Invoke-RestMethod "http://localhost:8000/api/v1/prices/topmovers"
```

`/topmovers` needs real historical price changes across separate runs. If the market prices have not changed yet, movers may still be empty even though ingestion is working correctly and history is accumulating.
