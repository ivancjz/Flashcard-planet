# Backfill Missing Prices and Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After every scheduled ingestion run, automatically re-fetch Pokemon TCG API data for assets that are missing a price or an image, logging diagnostic counts.

**Architecture:** A new `run_backfill_pass()` function in `pokemon_tcg.py` queries the DB for assets with `metadata_json["images"]["small"]` empty/null or no `PriceHistory` row for the primary source, collects their `provider_card_id` from `metadata_json`, and runs them through the existing `fetch_card` + `build_asset_payload` + `add_price_point` path. `_run_scheduled_ingestion()` in `scheduler.py` calls it inside the existing `finally` block, after gap detection. A `BACKFILL_BATCH_SIZE` config field caps the number of cards per run.

**Tech Stack:** Python, SQLAlchemy 2.x, PostgreSQL (JSONB operators), existing `pokemon_tcg.py` helpers.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/app/ingestion/pokemon_tcq.py` | Modify | Add `run_backfill_pass()` + `BackfillResult` dataclass |
| `backend/app/backstage/scheduler.py` | Modify | Call `run_backfill_pass()` after gap detection |
| `backend/app/core/config.py` | Modify | Add `backfill_batch_size: int` field |
| `.env.example` | Modify | Document `BACKFILL_BATCH_SIZE` |
| `tests/test_backfill.py` | Create | Query logic + callable tests |

---

## Task 1: Config field + query helpers

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `.env.example`
- Create: `tests/test_backfill.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_backfill.py`:

```python
"""Tests for the backfill pass (missing prices + images)."""
from __future__ import annotations

import unittest


class BackfillConfigTests(unittest.TestCase):
    def test_backfill_batch_size_default(self):
        from backend.app.core.config import get_settings
        s = get_settings()
        self.assertEqual(s.backfill_batch_size, 100)

    def test_backfill_batch_size_respects_env(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"BACKFILL_BATCH_SIZE": "25"}):
            from backend.app.core import config as c
            import importlib
            importlib.reload(c)
            self.assertEqual(c.Settings().backfill_batch_size, 25)


class BackfillFunctionTests(unittest.TestCase):
    def test_run_backfill_pass_is_callable(self):
        from backend.app.ingestion.pokemon_tcg import run_backfill_pass
        self.assertTrue(callable(run_backfill_pass))

    def test_backfill_result_has_expected_fields(self):
        from backend.app.ingestion.pokemon_tcg import BackfillResult
        r = BackfillResult()
        self.assertEqual(r.missing_price, 0)
        self.assertEqual(r.missing_image, 0)
        self.assertEqual(r.attempted, 0)
        self.assertEqual(r.price_filled, 0)
        self.assertEqual(r.image_filled, 0)
        self.assertEqual(r.skipped_no_price, 0)
        self.assertEqual(r.errors, 0)
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd c:/Flashcard-planet
python -m pytest tests/test_backfill.py -v
```

Expected: `ImportError` — `backfill_batch_size` and `run_backfill_pass` not yet defined.

- [ ] **Step 3: Add `backfill_batch_size` to `config.py`**

In `backend/app/core/config.py`, add this line after `gap_set_coverage_threshold`:

```python
    backfill_batch_size: int = Field(default=100, ge=1, le=1000)
```

- [ ] **Step 4: Add `BACKFILL_BATCH_SIZE` to `.env.example`**

In `.env.example`, add after `GAP_SET_COVERAGE_THRESHOLD=0.5`:

```
# Maximum number of assets to backfill per scheduled run.
BACKFILL_BATCH_SIZE=100
```

- [ ] **Step 5: Add `BackfillResult` dataclass to `pokemon_tcg.py`**

In `backend/app/ingestion/pokemon_tcg.py`, add this dataclass after `IngestionResult`:

```python
@dataclass
class BackfillResult:
    missing_price: int = 0
    missing_image: int = 0
    attempted: int = 0
    price_filled: int = 0
    image_filled: int = 0
    skipped_no_price: int = 0
    errors: int = 0
```

- [ ] **Step 6: Add a stub `run_backfill_pass()` to `pokemon_tcg.py`**

Add this function at the bottom of `backend/app/ingestion/pokemon_tcg.py`:

```python
def run_backfill_pass(session: Session) -> BackfillResult:
    """Re-fetch Pokemon TCG API data for assets missing a price or image.

    Queries assets whose provider_card_id is stored in metadata_json but whose
    PriceHistory (primary source) or image is missing, then re-runs them through
    the normal fetch + ingest path. Capped at settings.backfill_batch_size per run.
    """
    return BackfillResult()
```

- [ ] **Step 7: Run tests to verify they pass**

```
cd c:/Flashcard-planet
python -m pytest tests/test_backfill.py -v
```

Expected: all 4 tests `PASS`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/config.py .env.example backend/app/ingestion/pokemon_tcg.py tests/test_backfill.py
git commit -m "feat: add BackfillResult + backfill_batch_size config (stub)"
```

---

## Task 2: Implement the gap queries

**Files:**
- Modify: `backend/app/ingestion/pokemon_tcg.py`
- Modify: `tests/test_backfill.py`

- [ ] **Step 1: Add query tests**

Append to `tests/test_backfill.py`:

```python
class BackfillQueryTests(unittest.TestCase):
    def test_query_missing_price_returns_card_ids(self):
        """_query_missing_price must return provider_card_id strings."""
        from unittest.mock import MagicMock, patch
        from backend.app.ingestion.pokemon_tcg import _query_missing_price

        mock_session = MagicMock()
        mock_row = MagicMock()
        mock_row.provider_card_id = "base1-4"
        mock_session.execute.return_value.all.return_value = [mock_row]

        result = _query_missing_price(mock_session, limit=10, primary_source="pokemon_tcg_api")
        self.assertEqual(result, ["base1-4"])

    def test_query_missing_image_returns_card_ids(self):
        """_query_missing_image must return provider_card_id strings."""
        from unittest.mock import MagicMock
        from backend.app.ingestion.pokemon_tcg import _query_missing_image

        mock_session = MagicMock()
        mock_row = MagicMock()
        mock_row.provider_card_id = "base1-6"
        mock_session.execute.return_value.all.return_value = [mock_row]

        result = _query_missing_image(mock_session, limit=10)
        self.assertEqual(result, ["base1-6"])
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd c:/Flashcard-planet
python -m pytest tests/test_backfill.py::BackfillQueryTests -v
```

Expected: `ImportError` — `_query_missing_price` and `_query_missing_image` not yet defined.

- [ ] **Step 3: Implement `_query_missing_price` in `pokemon_tcg.py`**

Add these imports at the top of `backend/app/ingestion/pokemon_tcg.py` if not already present:

```python
from sqlalchemy import func, literal_column, outerjoin, text
```

Add the function before `run_backfill_pass`:

```python
def _query_missing_price(session: Session, *, limit: int, primary_source: str) -> list[str]:
    """Return provider_card_id values for assets that have no PriceHistory row
    for primary_source. Only assets whose metadata_json contains a provider_card_id
    are included (i.e. cards originally ingested from Pokemon TCG API)."""
    from backend.app.models.asset import Asset
    from sqlalchemy import outerjoin

    subq = (
        select(
            Asset.id,
            Asset.metadata_json["provider_card_id"].astext.label("provider_card_id"),
        )
        .where(
            Asset.metadata_json.isnot(None),
            Asset.metadata_json["provider_card_id"].astext.isnot(None),
            Asset.metadata_json["provider_card_id"].astext != "",
            Asset.category == "Pokemon",
        )
        .subquery()
    )

    rows = session.execute(
        select(subq.c.provider_card_id)
        .outerjoin(
            PriceHistory,
            (PriceHistory.asset_id == subq.c.id)
            & (PriceHistory.source == primary_source),
        )
        .where(PriceHistory.id.is_(None))
        .limit(limit)
    ).all()

    return [row.provider_card_id for row in rows]
```

- [ ] **Step 4: Implement `_query_missing_image` in `pokemon_tcg.py`**

Add the function after `_query_missing_price`:

```python
def _query_missing_image(session: Session, *, limit: int) -> list[str]:
    """Return provider_card_id values for assets whose metadata_json is missing
    a non-empty images.small URL."""
    from backend.app.models.asset import Asset

    rows = session.execute(
        select(
            Asset.metadata_json["provider_card_id"].astext.label("provider_card_id"),
        )
        .where(
            Asset.metadata_json.isnot(None),
            Asset.metadata_json["provider_card_id"].astext.isnot(None),
            Asset.metadata_json["provider_card_id"].astext != "",
            Asset.category == "Pokemon",
            ~(
                Asset.metadata_json.has_key("images")
                & Asset.metadata_json["images"].has_key("small")
                & (Asset.metadata_json["images"]["small"].astext != "")
            ),
        )
        .limit(limit)
    ).all()

    return [row.provider_card_id for row in rows]
```

- [ ] **Step 5: Run tests to verify they pass**

```
cd c:/Flashcard-planet
python -m pytest tests/test_backfill.py -v
```

Expected: all 6 tests `PASS`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/ingestion/pokemon_tcg.py tests/test_backfill.py
git commit -m "feat: add _query_missing_price and _query_missing_image helpers"
```

---

## Task 3: Implement `run_backfill_pass()`

**Files:**
- Modify: `backend/app/ingestion/pokemon_tcg.py`
- Modify: `tests/test_backfill.py`

- [ ] **Step 1: Add the integration test**

Append to `tests/test_backfill.py`:

```python
class RunBackfillPassTests(unittest.TestCase):
    def test_returns_backfill_result_when_no_gaps(self):
        """run_backfill_pass returns a BackfillResult with zeros when no gaps exist."""
        from unittest.mock import MagicMock, patch
        from backend.app.ingestion.pokemon_tcg import run_backfill_pass

        mock_session = MagicMock()

        with patch("backend.app.ingestion.pokemon_tcg._query_missing_price", return_value=[]) as mp, \
             patch("backend.app.ingestion.pokemon_tcg._query_missing_image", return_value=[]) as mi:
            result = run_backfill_pass(mock_session)

        self.assertEqual(result.attempted, 0)
        self.assertEqual(result.missing_price, 0)
        self.assertEqual(result.missing_image, 0)

    def test_returns_backfill_result_with_counts_when_gaps_exist(self):
        """run_backfill_pass attempts re-ingestion for cards in the gap lists."""
        from unittest.mock import MagicMock, patch
        from backend.app.ingestion.pokemon_tcg import run_backfill_pass, BackfillResult

        mock_session = MagicMock()
        fake_card = {
            "id": "base1-4",
            "name": "Charizard",
            "images": {"small": "https://example.com/charizard.png"},
            "set": {"name": "Base Set", "id": "base1"},
            "number": "4",
            "tcgplayer": {"prices": {"holofoil": {"market": 350.0}}},
        }

        with patch("backend.app.ingestion.pokemon_tcg._query_missing_price", return_value=["base1-4"]), \
             patch("backend.app.ingestion.pokemon_tcg._query_missing_image", return_value=[]), \
             patch("backend.app.ingestion.pokemon_tcg.fetch_card", return_value=fake_card), \
             patch("backend.app.ingestion.pokemon_tcg.stage_observation_match") as mock_obs, \
             patch("backend.app.ingestion.pokemon_tcg.add_price_point") as mock_price:
            obs_result = MagicMock()
            obs_result.can_write_price_history = True
            obs_result.matched_asset = MagicMock()
            obs_result.matched_asset.id = "some-uuid"
            obs_result.matched_asset.metadata_json = {"images": {"small": "https://example.com/charizard.png"}}
            mock_obs.return_value = obs_result
            mock_price.return_value = MagicMock(inserted=True, price_changed=True)

            result = run_backfill_pass(mock_session)

        self.assertEqual(result.missing_price, 1)
        self.assertEqual(result.attempted, 1)
```

- [ ] **Step 2: Run the test to verify it fails**

```
cd c:/Flashcard-planet
python -m pytest tests/test_backfill.py::RunBackfillPassTests -v
```

Expected: `FAIL` — `run_backfill_pass` returns an empty `BackfillResult` (stub).

- [ ] **Step 3: Implement `run_backfill_pass()` fully**

Replace the stub `run_backfill_pass` in `backend/app/ingestion/pokemon_tcg.py` with:

```python
def run_backfill_pass(session: Session) -> BackfillResult:
    """Re-fetch Pokemon TCG API data for assets missing a price or image.

    Queries assets whose provider_card_id is stored in metadata_json but whose
    PriceHistory (primary source) or image is missing, then re-runs them through
    the normal fetch + ingest path. Capped at settings.backfill_batch_size per run.
    """
    settings = get_settings()
    result = BackfillResult()
    batch_size = settings.backfill_batch_size

    missing_price_ids = _query_missing_price(
        session, limit=batch_size, primary_source=POKEMON_TCG_PRICE_SOURCE
    )
    missing_image_ids = _query_missing_image(session, limit=batch_size)

    result.missing_price = len(missing_price_ids)
    result.missing_image = len(missing_image_ids)

    # Deduplicate: a card may appear in both lists
    to_backfill = list(dict.fromkeys(missing_price_ids + missing_image_ids))[:batch_size]

    if not to_backfill:
        logger.info(
            '{"event": "backfill_skipped", "reason": "no_gaps_found"}'
        )
        return result

    logger.info(
        '{"event": "backfill_started", "missing_price": %d, "missing_image": %d, "to_backfill": %d}',
        result.missing_price,
        result.missing_image,
        len(to_backfill),
    )

    ingested_at = datetime.now(UTC).replace(microsecond=0)

    with httpx.Client(timeout=20.0, headers=build_headers()) as client:
        for card_id in to_backfill:
            result.attempted += 1
            had_image_before = False
            try:
                card = fetch_card(client, card_id)
                chosen_price = choose_price_snapshot(card)

                if chosen_price is None:
                    result.skipped_no_price += 1
                    logger.warning(
                        '{"event": "backfill_card_skipped", "card_id": "%s", "reason": "no_price"}',
                        card_id,
                    )
                    continue

                price_source, price_field, price = chosen_price
                asset_payload = build_asset_payload(card, price_source, price_field)

                observation_result = stage_observation_match(
                    session,
                    provider=POKEMON_TCG_PRICE_SOURCE,
                    external_item_id=card["id"],
                    raw_title=card.get("name"),
                    raw_set_name=card.get("set", {}).get("name"),
                    raw_card_number=card.get("number"),
                    raw_language=extract_raw_language(card),
                    asset_payload=asset_payload,
                )

                if not observation_result.can_write_price_history or observation_result.matched_asset is None:
                    result.errors += 1
                    continue

                asset = observation_result.matched_asset
                had_image_before = bool(
                    (asset.metadata_json or {}).get("images", {}).get("small")
                )

                insert_result = add_price_point(
                    session,
                    asset_id=asset.id,
                    source=POKEMON_TCG_PRICE_SOURCE,
                    currency="USD",
                    price=price,
                    captured_at=ingested_at,
                )
                if insert_result.inserted:
                    result.price_filled += 1

                # Check if image was written by observation_match updating metadata_json
                has_image_now = bool(
                    (asset.metadata_json or {}).get("images", {}).get("small")
                )
                if not had_image_before and has_image_now:
                    result.image_filled += 1

            except Exception as exc:  # noqa: BLE001
                result.errors += 1
                logger.warning(
                    '{"event": "backfill_card_error", "card_id": "%s", "error": "%s"}',
                    card_id,
                    str(exc),
                )

    logger.info(
        '{"event": "backfill_complete", "attempted": %d, "price_filled": %d, "image_filled": %d, "skipped_no_price": %d, "errors": %d}',
        result.attempted,
        result.price_filled,
        result.image_filled,
        result.skipped_no_price,
        result.errors,
    )
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd c:/Flashcard-planet
python -m pytest tests/test_backfill.py -v
```

Expected: all 8 tests `PASS`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/ingestion/pokemon_tcg.py tests/test_backfill.py
git commit -m "feat: implement run_backfill_pass() — re-fetches cards missing price or image"
```

---

## Task 4: Hook backfill into the scheduler

**Files:**
- Modify: `backend/app/backstage/scheduler.py`
- Modify: `tests/test_backfill.py`

- [ ] **Step 1: Add the scheduler integration test**

Append to `tests/test_backfill.py`:

```python
class SchedulerBackfillTests(unittest.TestCase):
    def test_run_backfill_pass_called_in_scheduled_ingestion(self):
        """_run_scheduled_ingestion must call run_backfill_pass once per run."""
        from unittest.mock import MagicMock, patch, call
        import backend.app.backstage.scheduler as sched

        with patch.object(sched, "_run_signal_sweep"), \
             patch.object(sched, "_evaluate_alerts"), \
             patch("backend.app.backstage.scheduler.get_tracked_pokemon_pools", return_value=[]), \
             patch("backend.app.backstage.scheduler.get_configured_provider_ingestors", return_value=[]), \
             patch("backend.app.backstage.scheduler.get_gap_report", return_value=MagicMock()), \
             patch("backend.app.backstage.scheduler.run_backfill_pass") as mock_backfill, \
             patch("backend.app.backstage.scheduler.SessionLocal") as mock_session_cls:
            mock_session = MagicMock()
            mock_session.__enter__ = MagicMock(return_value=mock_session)
            mock_session.__exit__ = MagicMock(return_value=False)
            mock_session_cls.return_value = mock_session
            mock_backfill.return_value = MagicMock(
                missing_price=0, missing_image=0, attempted=0,
                price_filled=0, image_filled=0, skipped_no_price=0, errors=0,
            )

            sched._run_scheduled_ingestion()

        mock_backfill.assert_called_once()
```

- [ ] **Step 2: Run the test to verify it fails**

```
cd c:/Flashcard-planet
python -m pytest tests/test_backfill.py::SchedulerBackfillTests -v
```

Expected: `FAIL` — `run_backfill_pass` is never called.

- [ ] **Step 3: Import `run_backfill_pass` in `scheduler.py`**

In `backend/app/backstage/scheduler.py`, add to the existing imports at the top:

```python
from backend.app.ingestion.pokemon_tcg import run_backfill_pass
```

- [ ] **Step 4: Call `run_backfill_pass` in `_run_scheduled_ingestion`**

In `_run_scheduled_ingestion`, inside the `finally` block after the gap detection block (after line ~272), add:

```python
        try:
            with SessionLocal() as session:
                run_backfill_pass(session)
        except Exception as exc:
            run.errors.append(f"Backfill pass failed: {exc}")
            logger.exception("Backfill pass after scheduled ingestion failed.")
```

The final `finally` block should look like:

```python
    finally:
        try:
            with SessionLocal() as session:
                run.gap_report = get_gap_report(session)
            _log_gap_report(run.gap_report)
        except Exception as exc:
            run.errors.append(f"Gap detection failed: {exc}")
            logger.exception("Gap detection after scheduled ingestion failed.")

        try:
            with SessionLocal() as session:
                run_backfill_pass(session)
        except Exception as exc:
            run.errors.append(f"Backfill pass failed: {exc}")
            logger.exception("Backfill pass after scheduled ingestion failed.")

        run.ended_at = datetime.now(UTC).replace(microsecond=0)
        logger.info(
            "Scheduled ingestion run finished. start_time=%s end_time=%s records_written=%s card_failures=%s errors=%s",
            run.started_at.isoformat(),
            run.ended_at.isoformat(),
            run.records_written,
            run.card_failures,
            run.errors if run.errors else "<none>",
        )
```

- [ ] **Step 5: Run the full test suite**

```
cd c:/Flashcard-planet
python -m pytest tests/ -v -q
```

Expected: all tests `PASS`, no regressions.

- [ ] **Step 6: Commit**

```bash
git add backend/app/backstage/scheduler.py tests/test_backfill.py
git commit -m "feat: call run_backfill_pass() after each scheduled ingestion run"
```

---

## Self-Review

**Spec coverage:**
- ✅ Backfill pass runs automatically after each scheduled ingestion — Task 4
- ✅ Missing price detected via LEFT JOIN on PriceHistory — Task 2
- ✅ Missing image detected via JSONB path check — Task 2
- ✅ Existing `fetch_card` / `build_asset_payload` / `add_price_point` reused — Task 3
- ✅ `BACKFILL_BATCH_SIZE` config field with default 100 — Task 1
- ✅ Diagnostic counts logged at INFO level — Task 3 (`backfill_started`, `backfill_complete`)
- ✅ Per-card errors logged at WARNING level without crashing the run — Task 3
- ✅ Backfill failure doesn't crash the overall scheduled run (wrapped in try/except) — Task 4

**Placeholder scan:** None found.

**Type consistency:** `BackfillResult` defined in Task 1 Step 5, used in Task 3 Step 3 and Task 4 Step 1 — fields match. `_query_missing_price` / `_query_missing_image` signatures defined in Task 2, called in Task 3 with matching keyword args.
