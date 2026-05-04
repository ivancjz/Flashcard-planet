# One Piece TCG Phase 1 Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire One Piece TCG as a third live game using optcgapi.com (free) as catalog + price source, with a 12h interval kill-switched scheduler job and Lesson-6-safe two-pass DB write.

**Architecture:** `OptcgapiClient` in `game_data/` fetches cards per set. `ingest_onepiece_sets()` iterates 5 seed sets; per-set errors are caught and continue. `_persist_cards()` does two passes per card: always upsert `Asset` (Pass 1), write `PriceHistory` only when `price > 0` (Pass 2), both in one transaction. `ONEPIECE_INGEST_ENABLED` env var gates the scheduler job.

**Tech Stack:** Python 3.13, SQLAlchemy 2, APScheduler, httpx, pytest, SQLite in-memory (tests only)

**Implementation timing:** After TASK-301 Pro launch ships. Spec is parked — do not start early.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/app/ingestion/game_data/optcgapi_client.py` | Create | `OnePieceCard` dataclass, `APINotFoundError`, `OptcgapiClient.fetch_set_cards()` |
| `backend/app/ingestion/onepiece.py` | Create | `ingest_onepiece_sets()`, `_persist_cards()`, `_upsert_op_asset()`, `_write_op_price()` |
| `tests/test_onepiece_ingest.py` | Create | 6 TDD test cases, SQLite in-memory fixture |
| `backend/app/services/scheduler_run_log_service.py` | Modify line 29 | Add `JOB_ONEPIECE = "onepiece-ingestion"` |
| `backend/app/core/config.py` | Modify line 72 | Add `onepiece_ingest_enabled: bool = False` |
| `backend/app/backstage/scheduler.py` | Modify lines 12–20, 98, 355, ~935, ~1094 | Import, `_STARTUP_DELAY`, `_monitored_jobs`, runner fn, job registration |
| `BACKLOG.md` | Modify `needs_triage` section | Add TASK-202b |

---

## Task 1: `optcgapi_client.py` — HTTP client and types

**Files:**
- Create: `backend/app/ingestion/game_data/optcgapi_client.py`

- [ ] **Step 1: Discover optcgapi.com endpoint shape before writing the client**

Run these to verify field names and URL pattern. Update the constants in Step 2 to match:

```bash
# List available API endpoints (Django REST Framework root)
curl -s https://optcgapi.com/api/ | python -m json.tool

# Cards for a known set — try the two most likely URL patterns
curl -s "https://optcgapi.com/api/cards/?set_id=OP01" | python -m json.tool | head -60
curl -s "https://optcgapi.com/api/sets/OP01/cards/" | python -m json.tool | head -60

# Confirm 404 vs 200+empty for a non-existent set (determines APINotFoundError trigger)
curl -s -o /dev/null -w "%{http_code}" "https://optcgapi.com/api/cards/?set_id=XXXX"
```

Confirm: (a) which URL returns cards, (b) exact field names for card number / rarity / market price, (c) whether a missing set returns HTTP 404 (→ raise `APINotFoundError`) or HTTP 200 + `[]` (→ return empty list and let caller record `"empty"`).

- [ ] **Step 2: Create `optcgapi_client.py`**

Update `_CARDS_PATH` and field names in `_parse_card()` to match Step 1 findings before committing.

```python
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import httpx

from backend.app.models.game import Game

logger = logging.getLogger(__name__)

_BASE_URL = "https://optcgapi.com"
_CARDS_PATH = "/api/cards/"   # update if Step 1 shows a different path


class APINotFoundError(Exception):
    """Raised when optcgapi.com returns 404 for a requested set code."""


@dataclass(frozen=True)
class OnePieceCard:
    card_number: str          # "OP01-060"
    name: str
    set_code: str             # "OP01"
    set_name: str             # "Romance Dawn"
    rarity: str               # "Super Rare"
    market_price: Decimal | None
    image_url: str | None


def _parse_price(raw: object) -> Decimal | None:
    if raw is None:
        return None
    try:
        value = Decimal(str(raw))
        return value if value > 0 else None
    except InvalidOperation:
        return None


def _parse_card(raw: dict, set_code: str) -> OnePieceCard:
    """Parse one raw API dict into OnePieceCard.

    Key names below are assumed from typical optcgapi.com responses.
    Update after verifying with Step 1 curl output.
    """
    return OnePieceCard(
        card_number=raw["id"],              # e.g. "OP01-060" — update key if different
        name=raw["name"],
        set_code=set_code,
        set_name=raw.get("set_name", ""),
        rarity=raw.get("rarity", ""),
        market_price=_parse_price(raw.get("market_price")),
        image_url=raw.get("image_url"),
    )


class OptcgapiClient:
    """HTTP client for optcgapi.com — OPTCG card catalog and TCGPlayer prices."""

    game = Game.ONE_PIECE
    rate_limit_per_second = 2.0   # conservative — no published limit

    def __init__(self) -> None:
        self._http = httpx.Client(
            base_url=_BASE_URL,
            timeout=20.0,
            headers={"User-Agent": "FlashcardPlanet/1.0"},
        )

    def fetch_set_cards(self, set_code: str) -> list[OnePieceCard]:
        """Return all cards for a set code.

        Raises APINotFoundError on 404 (expected for OP13 until optcgapi adds it).
        Returns [] if set exists but has no cards.
        Raises httpx.HTTPStatusError for other HTTP errors.
        """
        try:
            resp = self._http.get(_CARDS_PATH, params={"set_id": set_code})
        except httpx.RequestError as exc:
            raise httpx.RequestError(f"Network error fetching {set_code}: {exc}") from exc

        if resp.status_code == 404:
            raise APINotFoundError(f"Set {set_code!r} not found in optcgapi.com")

        resp.raise_for_status()

        raw_list: object = resp.json()
        # Handle both bare list and {"results": [...]} wrapper
        if isinstance(raw_list, dict):
            raw_list = raw_list.get("results", [])
        if not isinstance(raw_list, list):
            logger.warning("optcgapi_unexpected_response_shape set_code=%s", set_code)
            return []

        cards: list[OnePieceCard] = []
        for raw in raw_list:
            try:
                cards.append(_parse_card(raw, set_code))
            except (KeyError, TypeError):
                logger.warning(
                    "optcgapi_card_parse_failed set_code=%s raw_keys=%s",
                    set_code,
                    list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__,
                )
        return cards
```

- [ ] **Step 3: Verify module imports cleanly**

```bash
python -c "from backend.app.ingestion.game_data.optcgapi_client import OptcgapiClient, OnePieceCard, APINotFoundError; print('OK')"
```

Expected output: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/ingestion/game_data/optcgapi_client.py
git commit -m "feat(onepiece): add OptcgapiClient + OnePieceCard + APINotFoundError (TASK-202)"
```

---

## Task 2: Failing tests

**Files:**
- Create: `tests/test_onepiece_ingest.py`

- [ ] **Step 1: Create the test file with all 6 failing tests**

```python
"""
tests/test_onepiece_ingest.py

TDD tests for One Piece TCG ingestion (TASK-202).
Pattern mirrors tests/test_ygo_ingest_segment.py.

Run: pytest tests/test_onepiece_ingest.py -v
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from sqlalchemy import JSON, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import backend.app.models  # noqa: F401 — registers all models with Base
from backend.app.db.base import Base
from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory


# ── SQLite in-memory fixture ───────────────────────────────────────────────────

def _coerce_postgres_types() -> None:
    """Replace JSONB columns with JSON so SQLite accepts the schema."""
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()


@contextmanager
def _session():
    _coerce_postgres_types()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as db:
        yield db
    Base.metadata.drop_all(engine)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fake_card(
    card_number: str = "OP01-060",
    name: str = "Monkey D. Luffy",
    set_code: str = "OP01",
    rarity: str = "Super Rare",
    market_price: Decimal | None = Decimal("12.50"),
) -> "OnePieceCard":
    from backend.app.ingestion.game_data.optcgapi_client import OnePieceCard
    return OnePieceCard(
        card_number=card_number,
        name=name,
        set_code=set_code,
        set_name="Romance Dawn",
        rarity=rarity,
        market_price=market_price,
        image_url="https://example.com/card.jpg",
    )


def _mock_client(cards: list) -> MagicMock:
    """Return a mock OptcgapiClient whose fetch_set_cards returns `cards` for every set."""
    mock = MagicMock()
    mock.fetch_set_cards.return_value = cards
    mock.rate_limit_per_second = 2.0
    return mock


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestOnePieceIngest:

    def test_asset_created_when_price_zero(self):
        """Pass 1 always upserts Asset; Pass 2 skips PriceHistory when price=0."""
        from backend.app.ingestion.onepiece import ingest_onepiece_sets

        mock = _mock_client([_fake_card(market_price=Decimal("0"))])

        with _session() as db:
            with (
                patch("backend.app.ingestion.onepiece.OptcgapiClient", return_value=mock),
                patch("backend.app.ingestion.onepiece.time.sleep"),
            ):
                ingest_onepiece_sets(db)

            assets = db.execute(select(Asset).where(Asset.game == "one_piece")).scalars().all()
            prices = db.execute(select(PriceHistory)).scalars().all()

        assert len(assets) == 1, "Asset must exist even when price=0"
        assert len(prices) == 0, "No PriceHistory when price=0"

    def test_asset_created_when_price_null(self):
        """Pass 1 always upserts Asset; Pass 2 skips PriceHistory when price=None."""
        from backend.app.ingestion.onepiece import ingest_onepiece_sets

        mock = _mock_client([_fake_card(market_price=None)])

        with _session() as db:
            with (
                patch("backend.app.ingestion.onepiece.OptcgapiClient", return_value=mock),
                patch("backend.app.ingestion.onepiece.time.sleep"),
            ):
                ingest_onepiece_sets(db)

            assets = db.execute(select(Asset).where(Asset.game == "one_piece")).scalars().all()
            prices = db.execute(select(PriceHistory)).scalars().all()

        assert len(assets) == 1, "Asset must exist even when price=None"
        assert len(prices) == 0, "No PriceHistory when price=None"

    def test_asset_and_price_written_when_price_positive(self):
        """Asset + PriceHistory both written when price > 0. market_segment must be 'raw'."""
        from backend.app.ingestion.onepiece import ingest_onepiece_sets

        mock = _mock_client([_fake_card(market_price=Decimal("12.50"))])

        with _session() as db:
            with (
                patch("backend.app.ingestion.onepiece.OptcgapiClient", return_value=mock),
                patch("backend.app.ingestion.onepiece.time.sleep"),
            ):
                ingest_onepiece_sets(db)

            assets = db.execute(select(Asset).where(Asset.game == "one_piece")).scalars().all()
            prices = db.execute(select(PriceHistory)).scalars().all()

        assert len(assets) == 1
        assert len(prices) == 1
        assert prices[0].market_segment == "raw", (
            f"market_segment must be 'raw' — explicit code contract, got {prices[0].market_segment!r}"
        )
        assert prices[0].price == Decimal("12.50")
        assert prices[0].source == "optcgapi"

    def test_upsert_idempotent_on_duplicate_external_id(self):
        """Same card appearing twice in the API response creates only one Asset row."""
        from backend.app.ingestion.onepiece import ingest_onepiece_sets

        card = _fake_card()
        mock = _mock_client([card, card])  # duplicate

        with _session() as db:
            with (
                patch("backend.app.ingestion.onepiece.OptcgapiClient", return_value=mock),
                patch("backend.app.ingestion.onepiece.time.sleep"),
            ):
                ingest_onepiece_sets(db)

            assets = db.execute(select(Asset).where(Asset.game == "one_piece")).scalars().all()

        assert len(assets) == 1, "Duplicate card in API response must not create duplicate Asset"

    def test_persist_continues_after_individual_card_failure(self):
        """When _upsert_op_asset raises for one card, the other cards are still processed."""
        from backend.app.ingestion.onepiece import _persist_cards

        card_a = _fake_card(card_number="OP01-001", name="Luffy", market_price=Decimal("5.00"))
        card_b = _fake_card(card_number="OP01-002", name="Nami", market_price=Decimal("3.00"))
        captured_at = datetime.now(UTC)

        with _session() as db:
            # Pre-create asset_b so the mock can return it
            asset_b = Asset(
                id=uuid.uuid4(),
                asset_class="TCG",
                game="one_piece",
                name="Nami",
                set_name="Romance Dawn",
                card_number="OP01-002",
                language="EN",
                variant="Super Rare",
                external_id="OP01-002|Super Rare",
            )
            db.add(asset_b)
            db.flush()

            with patch("backend.app.ingestion.onepiece._upsert_op_asset") as mock_upsert:
                # card_a raises, card_b succeeds
                mock_upsert.side_effect = [Exception("simulated upsert failure"), (asset_b, False)]
                assets_created, prices_inserted = _persist_cards(db, [card_a, card_b], captured_at)

            prices = db.execute(select(PriceHistory)).scalars().all()

        assert assets_created == 0   # card_b was pre-existing (created=False), card_a failed
        assert prices_inserted == 1, "card_b price must be written despite card_a failure"
        assert prices[0].source == "optcgapi"

    def test_api_not_found_continues_next_set(self):
        """APINotFoundError for OP13 is recorded as 'not_found_in_source'; other sets succeed."""
        from backend.app.ingestion.onepiece import ingest_onepiece_sets, ONEPIECE_SETS
        from backend.app.ingestion.game_data.optcgapi_client import APINotFoundError

        def side_effect(set_code: str) -> list:
            if set_code == "OP13":
                raise APINotFoundError(f"Set {set_code!r} not found")
            return [_fake_card(card_number=f"{set_code}-001", set_code=set_code)]

        mock = MagicMock()
        mock.fetch_set_cards.side_effect = side_effect
        mock.rate_limit_per_second = 2.0

        with _session() as db:
            with (
                patch("backend.app.ingestion.onepiece.OptcgapiClient", return_value=mock),
                patch("backend.app.ingestion.onepiece.time.sleep"),
            ):
                result = ingest_onepiece_sets(db)

        assert result.per_set.get("OP13") == "not_found_in_source", (
            f"Expected 'not_found_in_source' for OP13, got {result.per_set.get('OP13')!r}"
        )
        for s in ONEPIECE_SETS:
            if s != "OP13":
                assert result.per_set.get(s, "").startswith("success"), (
                    f"Set {s} should have succeeded, got {result.per_set.get(s)!r}"
                )
```

- [ ] **Step 2: Run tests — confirm they all fail with ImportError**

```bash
pytest tests/test_onepiece_ingest.py -v 2>&1 | head -20
```

Expected: all 6 fail with `ModuleNotFoundError: No module named 'backend.app.ingestion.onepiece'`.

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_onepiece_ingest.py
git commit -m "test(onepiece): 6 failing TDD tests for ingestion (TASK-202)"
```

---

## Task 3: `onepiece.py` — make tests pass

**Files:**
- Create: `backend/app/ingestion/onepiece.py`

- [ ] **Step 1: Create `onepiece.py`**

```python
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.app.ingestion.game_data.optcgapi_client import (
    APINotFoundError,
    OnePieceCard,
    OptcgapiClient,
)
from backend.app.models.asset import Asset
from backend.app.models.price_history import PriceHistory

logger = logging.getLogger(__name__)

ONEPIECE_SETS = ["OP01", "OP05", "OP08", "OP09", "OP13"]
ONEPIECE_PRICE_SOURCE = "optcgapi"


@dataclass
class OnePieceIngestionResult:
    sets_attempted: list[str] = field(default_factory=list)
    assets_created: int = 0
    price_points_inserted: int = 0
    per_set: dict[str, str] = field(default_factory=dict)
    captured_at: datetime | None = None


def _upsert_op_asset(session: Session, card: OnePieceCard) -> tuple[Asset, bool]:
    """Return (asset, created). Always upserts regardless of price — Lesson 6."""
    external_id = f"{card.card_number}|{card.rarity}"

    existing = session.scalars(
        select(Asset).where(Asset.external_id == external_id)
    ).first()
    if existing:
        return existing, False

    asset = Asset(
        id=uuid.uuid4(),
        asset_class="TCG",
        game="one_piece",
        category=card.rarity or "One Piece TCG",
        name=card.name,
        set_name=card.set_name,
        card_number=card.card_number,
        language="EN",
        variant=card.rarity,
        external_id=external_id,
        metadata_json={
            "set": {
                "id": card.set_code,
                "name": card.set_name,
                "total": None,
            },
            "rarity": card.rarity,
            "image_url": card.image_url,
            "images": {"small": card.image_url},
        },
    )
    session.add(asset)
    session.flush()
    return asset, True


def _write_op_price(
    session: Session,
    asset_id: uuid.UUID,
    price: Decimal,
    captured_at: datetime,
) -> bool:
    """Insert PriceHistory. market_segment='raw' is explicit — never relies on DB default."""
    stmt = pg_insert(PriceHistory).values(
        id=uuid.uuid4(),
        asset_id=asset_id,
        source=ONEPIECE_PRICE_SOURCE,
        currency="USD",
        price=price,
        captured_at=captured_at,
        market_segment="raw",
    ).on_conflict_do_nothing()
    rows = session.execute(stmt)
    return bool(rows.rowcount)


def _persist_cards(
    session: Session,
    cards: list[OnePieceCard],
    captured_at: datetime,
) -> tuple[int, int]:
    """Two-pass DB write. Returns (assets_created, price_points_inserted).

    Pass 1: always upsert Asset — price field is irrelevant (Lesson 6).
    Pass 2: write PriceHistory only when price > 0.
    One transaction — both passes committed together.
    """
    assets_created = 0
    price_points_inserted = 0

    for card in cards:
        try:
            asset, created = _upsert_op_asset(session, card)
            if created:
                assets_created += 1
        except Exception:
            logger.warning(
                "onepiece_asset_upsert_failed card_number=%s name=%s",
                card.card_number,
                card.name,
                exc_info=True,
            )
            continue

        price = card.market_price or Decimal("0")
        if price > 0:
            if _write_op_price(session, asset.id, price, captured_at):
                price_points_inserted += 1

    session.commit()
    return assets_created, price_points_inserted


def ingest_onepiece_sets(session: Session) -> OnePieceIngestionResult:
    """Fetch OPTCG cards from optcgapi.com and upsert assets + price_history.

    Per-set errors are caught — one set failing does not affect other sets.
    OP13 returning APINotFoundError is expected until optcgapi.com adds coverage.
    """
    result = OnePieceIngestionResult(
        sets_attempted=list(ONEPIECE_SETS),
        captured_at=datetime.now(UTC).replace(microsecond=0),
    )
    client = OptcgapiClient()
    rate_delay = 1.0 / client.rate_limit_per_second

    for set_code in ONEPIECE_SETS:
        try:
            cards = client.fetch_set_cards(set_code)
        except APINotFoundError:
            result.per_set[set_code] = "not_found_in_source"
            logger.info("onepiece_set_not_in_source set_code=%s", set_code)
            time.sleep(rate_delay)
            continue
        except Exception:
            result.per_set[set_code] = "failed: fetch error"
            logger.exception("onepiece_set_fetch_failed set_code=%s", set_code)
            time.sleep(rate_delay)
            continue

        if not cards:
            result.per_set[set_code] = "empty"
            time.sleep(rate_delay)
            continue

        try:
            created, inserted = _persist_cards(session, cards, result.captured_at)
        except Exception:
            result.per_set[set_code] = "failed: persist error"
            logger.exception("onepiece_set_persist_failed set_code=%s", set_code)
            time.sleep(rate_delay)
            continue

        result.per_set[set_code] = f"success ({len(cards)} cards)"
        result.assets_created += created
        result.price_points_inserted += inserted
        logger.info(
            "onepiece_set_done set_code=%s cards=%s assets_created=%s price_points=%s",
            set_code, len(cards), created, inserted,
        )
        time.sleep(rate_delay)

    logger.info(
        "onepiece_ingest_complete sets=%s assets_created=%s price_points=%s per_set=%s",
        len(ONEPIECE_SETS), result.assets_created, result.price_points_inserted, result.per_set,
    )
    return result
```

- [ ] **Step 2: Run the 6 new tests**

```bash
pytest tests/test_onepiece_ingest.py -v
```

Expected: all 6 pass. Fix any failures before continuing.

- [ ] **Step 3: Run the full suite to check for regressions**

```bash
pytest --tb=short -q 2>&1 | tail -5
```

Expected: 0 new failures. Note the new total (prior total + 6).

- [ ] **Step 4: Commit**

```bash
git add backend/app/ingestion/onepiece.py
git commit -m "feat(onepiece): ingest_onepiece_sets with two-pass Lesson-6-safe persist (TASK-202)"
```

---

## Task 4: Service layer — `scheduler_run_log_service.py` + `config.py`

**Files:**
- Modify: `backend/app/services/scheduler_run_log_service.py` (after line 28)
- Modify: `backend/app/core/config.py` (after line 71)

- [ ] **Step 1: Add `JOB_ONEPIECE` to `scheduler_run_log_service.py`**

After `JOB_YGO = "yugioh-ingestion"` (line 28), add one line:

```python
JOB_ONEPIECE     = "onepiece-ingestion"
```

The constant block now reads:

```python
JOB_INGESTION    = "ingestion"
JOB_BACKFILL     = "backfill"
JOB_RETRY        = "retry"
JOB_SIGNALS      = "signals"
JOB_EBAY         = "ebay-ingestion"
JOB_BULK_REFRESH = "bulk-set-price-refresh"
JOB_HEARTBEAT    = "alert-heartbeat"
JOB_YGO          = "yugioh-ingestion"
JOB_EXPLANATION  = "explanation-sweep"
JOB_DIGEST       = "market-digest-send"
JOB_ONEPIECE     = "onepiece-ingestion"
```

- [ ] **Step 2: Add `onepiece_ingest_enabled` to `config.py`**

After `ebay_scheduled_ingest_enabled: bool = False` (line 71), add:

```python
    onepiece_ingest_enabled: bool = False
```

- [ ] **Step 3: Verify both additions**

```bash
python -c "from backend.app.services.scheduler_run_log_service import JOB_ONEPIECE; print(JOB_ONEPIECE)"
python -c "from backend.app.core.config import Settings; print(Settings().onepiece_ingest_enabled)"
```

Expected:
```
onepiece-ingestion
False
```

- [ ] **Step 4: Run full suite**

```bash
pytest --tb=short -q 2>&1 | tail -5
```

Expected: 0 new failures.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/scheduler_run_log_service.py backend/app/core/config.py
git commit -m "feat(onepiece): add JOB_ONEPIECE constant and kill-switch config (TASK-202)"
```

---

## Task 5: `scheduler.py` — job runner and registration

**Files:**
- Modify: `backend/app/backstage/scheduler.py` (5 edits in one file)

- [ ] **Step 1: Add `JOB_ONEPIECE` to the import block**

Find the `from backend.app.services.scheduler_run_log_service import (...)` block near the top of the file (around lines 12–20). Add `JOB_ONEPIECE` to the list:

```python
from backend.app.services.scheduler_run_log_service import (
    JOB_BULK_REFRESH,
    JOB_DIGEST,
    JOB_EBAY,
    JOB_HEARTBEAT,
    JOB_INGESTION,
    JOB_ONEPIECE,
    JOB_RETRY,
    JOB_SIGNALS,
    JOB_YGO,
    JOB_EXPLANATION,
)
```

- [ ] **Step 2: Add startup delay entry**

In `_STARTUP_DELAY` (around line 90), after `"yugioh-ingestion": 780`, add:

```python
    "onepiece-ingestion":    840,   # 14 min — after YGO (780s), before bulk-refresh (900s)
```

Full ladder after this edit:

```python
_STARTUP_DELAY: dict[str, int] = {
    "scheduled-ingestion":    120,   #  2 min
    "signal-sweep":           600,   # 10 min
    "alert-heartbeat":        720,   # 12 min
    "ebay-ingestion":         660,   # 11 min
    "yugioh-ingestion":       780,   # 13 min
    "onepiece-ingestion":     840,   # 14 min
    "bulk-set-price-refresh": 900,   # 15 min
    "explanation-sweep":      960,   # 16 min
    "market-digest-send":    1200,   # 20 min
}
```

- [ ] **Step 3: Add `JOB_ONEPIECE` to `_monitored_jobs`**

Find (around line 355):

```python
_monitored_jobs = [JOB_EBAY, JOB_INGESTION, JOB_BULK_REFRESH, JOB_SIGNALS, JOB_YGO, JOB_EXPLANATION]
```

Replace with:

```python
_monitored_jobs = [JOB_EBAY, JOB_INGESTION, JOB_BULK_REFRESH, JOB_SIGNALS, JOB_YGO, JOB_EXPLANATION, JOB_ONEPIECE]
```

- [ ] **Step 4: Add `_run_onepiece_ingestion()` function**

After `_run_ygo_ingestion()` (after its closing `prune_old_runs` line, around line 934), insert:

```python
def _run_onepiece_ingestion() -> None:
    from backend.app.ingestion.onepiece import ingest_onepiece_sets

    try:
        with SessionLocal() as _log_session:
            _run_id = start_run(_log_session, JOB_ONEPIECE)
    except Exception as exc:
        logger.exception("start_run_failed job=%s", JOB_ONEPIECE)
        send_discord_alert(
            "error",
            f"CRITICAL: start_run 失败 — {JOB_ONEPIECE}",
            f"error={exc}\nJob 已跳过，本次无 run_log 记录",
        )
        return

    _records = 0
    _status = "error"
    _errors = 0
    _error_message: str | None = None
    _meta: dict | None = None

    try:
        with SessionLocal() as session:
            result = ingest_onepiece_sets(session)

        _records = result.price_points_inserted
        _meta = {"sets": result.per_set}

        failures = sum(1 for v in result.per_set.values() if v.startswith("failed"))
        successes = sum(1 for v in result.per_set.values() if v.startswith("success"))

        if failures == 0:
            _status = "success"      # includes "not_found_in_source" and "empty" — expected states
        elif successes > 0:
            _status = "partial"
            _errors = failures
        else:
            _status = "error"
            _errors = failures
            _error_message = f"All sets failed or missing: {result.per_set}"

        logger.info(
            "onepiece_ingestion_complete assets_created=%s price_points=%s per_set=%s",
            result.assets_created, result.price_points_inserted, result.per_set,
        )
    except Exception as exc:
        _status = "error"
        _errors = 1
        _error_message = str(exc)
        logger.exception("onepiece_ingestion_failed")
    finally:
        with SessionLocal() as _log_session:
            finish_run(
                _log_session, _run_id,
                status=_status,
                records_written=_records,
                errors=_errors,
                error_message=_error_message,
                meta_json=_meta,
            )
            prune_old_runs(_log_session, JOB_ONEPIECE)
```

- [ ] **Step 5: Register the job in `prepare_scheduler()`**

After the `scheduler.add_job(_run_ygo_ingestion, ...)` block (around line 1094), add:

```python
    if settings.onepiece_ingest_enabled:
        scheduler.add_job(
            _run_onepiece_ingestion,
            "interval",
            hours=12,
            id=JOB_ONEPIECE,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=None,
        )
```

- [ ] **Step 6: Run full suite**

```bash
pytest --tb=short -q 2>&1 | tail -5
```

Expected: 0 new failures.

- [ ] **Step 7: Commit**

```bash
git add backend/app/backstage/scheduler.py
git commit -m "feat(onepiece): wire onepiece-ingestion scheduler job with 12h interval + kill switch (TASK-202)"
```

---

## Task 6: BACKLOG.md — TASK-202b

**Files:**
- Modify: `BACKLOG.md` (append to `needs_triage` section)

- [ ] **Step 1: Add TASK-202b to the `needs_triage` section**

In the `### needs_triage (proposed by Claude Code or operator, not yet prioritized)` section, after the last existing entry, add:

```markdown
#### TASK-202b — OP13 data source gap (One Piece)
**Proposed:** 2026-05-04 (TASK-202 spike finding)
**Status:** deferred — do not start without operator approval
**Trigger:** optcgapi.com still has no OP13 coverage 30 days after `ONEPIECE_INGEST_ENABLED=true` **and** Plus/Pro users report missing OP13 cards.
**Options (decide at trigger time, not now):**
- Wait for optcgapi.com to add OP13 (passive)
- Test tcgapi.dev free tier for OP13 coverage
- Accelerate Phase 2: tcgapi.dev Pro ($49.99/mo) — standard Phase 2 trigger is ARR ≥ $5K
**Context:** OP01–OP12 covered by optcgapi.com. OP13 returns `not_found_in_source` per run — expected, not an error. See `docs/strategy/05_onepiece_integration.md` §2 and `docs/superpowers/specs/2026-05-04-onepiece-integration-design.md`.
```

- [ ] **Step 2: Commit**

```bash
git add BACKLOG.md
git commit -m "docs(backlog): add TASK-202b OP13 source gap deferred task (TASK-202)"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Implemented in |
|---|---|
| `optcgapi_client.py` + `OnePieceCard` + `APINotFoundError` | Task 1 |
| Endpoint discovery before implementing | Task 1 Step 1 |
| `ONEPIECE_SETS = ["OP01","OP05","OP08","OP09","OP13"]` | Task 3 |
| Two-pass persist, both passes in one transaction | Task 3 `_persist_cards()` |
| `market_segment="raw"` explicit, not DB default | Task 3 `_write_op_price()` |
| `external_id = f"{card_number}\|{rarity}"` | Task 3 `_upsert_op_asset()` |
| `source = "optcgapi"` | Task 3 `ONEPIECE_PRICE_SOURCE` |
| 6 TDD tests: price=0, price=None, price>0, idempotent, card failure continues, APINotFoundError continues | Task 2 |
| `market_segment == "raw"` asserted in test | Task 2 test 3 |
| `JOB_ONEPIECE = "onepiece-ingestion"` | Task 4 |
| `onepiece_ingest_enabled: bool = False` kill switch | Task 4 |
| `_STARTUP_DELAY["onepiece-ingestion"] = 840` | Task 5 Step 2 |
| `JOB_ONEPIECE` in `_monitored_jobs` (zero-output alert) | Task 5 Step 3 |
| `_run_onepiece_ingestion()` with start/finish/prune | Task 5 Step 4 |
| `meta_json = {"sets": result.per_set}` on finish_run | Task 5 Step 4 |
| 12h interval | Task 5 Step 5 |
| TASK-202b in BACKLOG.md | Task 6 |
| Operator action items | In spec doc only — no code needed |

**Placeholder scan:** None. Task 1 Step 1 contains a curl discovery step (actionable guidance, not a placeholder — the implementer executes it to find the real endpoint).

**Type consistency:**
- `OptcgapiClient` defined Task 1, imported in Task 3 ✓
- `OnePieceCard` defined Task 1, used in Tasks 2 + 3 ✓
- `APINotFoundError` defined Task 1, used in Tasks 2 + 3 ✓
- `OnePieceIngestionResult.per_set: dict[str, str]` defined Task 3, consumed Task 5 ✓
- `ingest_onepiece_sets(session)` defined Task 3, called Task 5 ✓
- `_persist_cards(session, cards, captured_at)` defined Task 3, tested Task 2 test 5 directly ✓
- `ONEPIECE_SETS` defined Task 3, imported in Task 2 test 6 ✓
- `JOB_ONEPIECE` defined Task 4, imported Task 5 ✓
- `finish_run(..., meta_json=...)` — confirmed signature in `scheduler_run_log_service.py:57` ✓
