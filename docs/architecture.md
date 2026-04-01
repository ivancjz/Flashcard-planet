# Flashcard Planet MVP Architecture

Flashcard Planet starts as a single Python monolith with two executable entry points:

- `backend.app.main` for the FastAPI API.
- `bot.main` for the Discord bot.

Both processes share the same database models and configuration to keep the MVP simple for one developer to run locally.

## Why this structure

- The universal `assets` model is category-agnostic, so Pokemon and sports cards can live in the same table.
- `price_history` stores observations over time rather than a single mutable price.
- `watchlists` and `alerts` separate the "user is interested in this asset" relationship from the specific alert rules attached to it.
- APScheduler is included as a lightweight place to hang future alert evaluation and ingestion jobs without introducing extra services yet.
