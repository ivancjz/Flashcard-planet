# Flashcard Planet

Flashcard Planet is a real-time card market intelligence MVP for trading cards and collectibles. This repository intentionally starts as a clean Python monolith: FastAPI for the backend API, PostgreSQL for persistence, and `discord.py` for the first bot interface.

## What is included

- FastAPI backend with a working price search endpoint and watchlist endpoints.
- PostgreSQL-ready SQLAlchemy models for `assets`, `price_history`, `users`, `watchlists`, and `alerts`.
- Universal asset model that can support Pokemon, sports cards, and future categories in the same schema.
- Discord bot scaffold with slash commands for `/price`, `/watch`, `/unwatch`, `/watchlist`, and `/topmovers`.
- APScheduler stub to give the MVP a practical place for future alert polling.
- Seed data script with a few cross-category sample assets.
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

### 4. Start PostgreSQL

If you have Docker available:

```powershell
docker compose up -d postgres
```

### 5. Initialize the schema and seed sample data

```powershell
python -m scripts.init_db
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

## First working API routes

- `GET /health`
- `GET /api/v1/prices/search?name=pikachu`
- `GET /api/v1/prices/topmovers`
- `POST /api/v1/watchlists`
- `GET /api/v1/watchlists/{discord_user_id}`
- `DELETE /api/v1/watchlists?discord_user_id=123&asset_name=Pikachu`

### Example watch payload

```json
{
  "discord_user_id": "1234567890",
  "asset_name": "Pikachu",
  "threshold_up_percent": 10,
  "threshold_down_percent": 5,
  "target_price": 11.5
}
```

## What is intentionally stubbed

- No live market data ingestion yet.
- No real alert evaluation yet; APScheduler currently logs a polling stub.
- No Discord-rich embeds or pagination yet.
- No migrations yet; schema creation is done with `create_all()` for MVP speed.
- No authentication or admin flows yet.

## Next practical steps

1. Add Alembic migrations before schema changes become frequent.
2. Implement a real price ingestion pipeline for one initial data source.
3. Build alert evaluation logic that compares the newest price to prior observations and pushes Discord notifications.
4. Improve asset search with better matching, filtering, and aliases.
5. Add basic tests for services and routes.
