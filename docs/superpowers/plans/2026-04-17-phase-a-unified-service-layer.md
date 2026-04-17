# Phase A: Unified Service Layer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish `DataService` + `ProGateConfig` as the single code path for all new feature work, so Phase B (Web) and Phase C (Bot deep links) share identical data shapes and permission logic.

**Architecture:** `core/response_types.py` holds shared dataclasses. `core/permissions.py` gains `get_pro_gate_config()`. `core/data_service.py` wraps existing `card_detail_service` and `signals_feed_service`, returning typed responses. A new API endpoint `/api/v1/cards/{external_id}/enriched` exposes DataService output as JSON for the Discord Bot (which uses HTTP, not direct imports). Existing routes in `site.py` and the Bot are untouched until Phase B/C.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy (sync Session), dataclasses, pytest, httpx (bot tests)

**Spec:** `docs/superpowers/specs/2026-04-17-v31-architecture-migration-design.md` — Phase A section

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `backend/app/core/response_types.py` | ProGateConfig, CardDetailResponse, SignalsResponse dataclasses |
| Modify | `backend/app/core/permissions.py` | Add `get_pro_gate_config(feature, access_tier)` |
| Create | `backend/app/core/data_service.py` | DataService class — wraps existing services |
| Create | `backend/app/api/routes/cards.py` | GET `/api/v1/cards/{external_id}/enriched` endpoint |
| Modify | `backend/app/api/router.py` | Register new cards router |
| Modify | `bot/api_client.py` | Add `fetch_card_detail_enriched(external_id, discord_user_id)` |
| Create | `backend/app/core/boundary_check.py` | Lint rules dict (CI documentation) |
| Create | `tests/test_response_types.py` | ProGateConfig unit tests |
| Create | `tests/test_data_service.py` | DataService unit tests |
| Create | `tests/test_cards_enriched_api.py` | Enriched endpoint integration tests |

---

## Pre-Task: Verify Existing Service Interfaces

Before writing any new code, confirm these three methods exist as expected:

```bash
cd c:/Flashcard-planet
grep -n "def build_card_detail\|def build_signals_feed" backend/app/services/card_detail_service.py backend/app/services/signals_feed_service.py
```

Expected output includes:
- `card_detail_service.py: def build_card_detail(db: Session, asset_id: uuid.UUID, *, access_tier: str) -> CardDetailViewModel | None`
- `signals_feed_service.py: def build_signals_feed(db: Session, access_tier: str, label_filter: str | None = None) -> SignalsFeedResult`

If signatures differ, adjust Task 3 accordingly before continuing.

---

## Task 1: `core/response_types.py` — Shared Dataclasses

**Files:**
- Create: `backend/app/core/response_types.py`
- Create: `tests/test_response_types.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_response_types.py
import pytest
from backend.app.core.response_types import ProGateConfig, CardDetailResponse, SignalsResponse
from decimal import Decimal
from datetime import datetime, timezone


class TestProGateConfig:
    def test_unlocked_config_returns_no_web_cta(self):
        cfg = ProGateConfig(is_locked=False)
        result = cfg.to_web_config()
        assert result["is_locked"] is False
        assert "ctaText" not in result

    def test_locked_config_to_web_config(self):
        cfg = ProGateConfig(
            is_locked=True,
            feature_name="Extended Price History",
            upgrade_reason="See long-term price patterns",
            urgency="medium",
        )
        result = cfg.to_web_config()
        assert result["maskType"] == "blur"
        assert result["ctaText"] == "Unlock Extended Price History — Pro Only"
        assert result["urgency"] == "medium"
        assert result["cssClass"] == "pro-gate-medium"

    def test_locked_config_to_bot_config(self):
        cfg = ProGateConfig(
            is_locked=True,
            feature_name="Extended Price History",
            upgrade_reason="See long-term price patterns",
            urgency="high",
        )
        result = cfg.to_bot_config()
        assert result["locked_message"] == "🔥 See long-term price patterns (Pro Only)"
        assert result["cta_text"] == "Upgrade to Pro for full access"
        assert result["upgrade_link"] == "/upgrade-from-discord"

    def test_bot_emoji_matches_urgency_medium(self):
        cfg = ProGateConfig(is_locked=True, upgrade_reason="x", urgency="medium")
        assert cfg.to_bot_config()["locked_message"].startswith("📈")

    def test_bot_emoji_matches_urgency_low(self):
        cfg = ProGateConfig(is_locked=True, upgrade_reason="x", urgency="low")
        assert cfg.to_bot_config()["locked_message"].startswith("💡")

    def test_unlocked_config_to_bot_config_returns_none(self):
        cfg = ProGateConfig(is_locked=False)
        assert cfg.to_bot_config() is None


class TestCardDetailResponse:
    def test_can_be_constructed_with_required_fields(self):
        response = CardDetailResponse(
            card_name="Charizard Base Set",
            external_id="base1-4",
            current_price=Decimal("150.00"),
            price_history=[],
            sample_size=47,
            match_confidence_avg=Decimal("0.85"),
            data_age="Updated 3 hours ago",
            source_breakdown={"eBay": 70, "TCG": 30},
            access_tier="free",
            pro_gate_config=None,
        )
        assert response.card_name == "Charizard Base Set"
        assert response.sample_size == 47


class TestSignalsResponse:
    def test_can_be_constructed(self):
        response = SignalsResponse(
            signals=[],
            total_eligible=10,
            access_tier="free",
            pro_gate_config=None,
        )
        assert response.total_eligible == 10
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd c:/Flashcard-planet
python -m pytest tests/test_response_types.py -v 2>&1 | head -30
```

Expected: `ImportError: cannot import name 'ProGateConfig' from 'backend.app.core.response_types'`

- [ ] **Step 3: Implement `response_types.py`**

```python
# backend/app/core/response_types.py
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

_URGENCY_EMOJI = {"high": "🔥", "medium": "📈", "low": "💡"}
_URGENCY_CSS = {"high": "pro-gate-high", "medium": "pro-gate-medium", "low": "pro-gate-low"}


@dataclass
class ProGateConfig:
    is_locked: bool
    feature_name: str = ""
    upgrade_reason: str = ""
    urgency: str = "medium"

    def to_web_config(self) -> dict:
        if not self.is_locked:
            return {"is_locked": False}
        return {
            "is_locked": True,
            "maskType": "blur",
            "ctaText": f"Unlock {self.feature_name} — Pro Only",
            "urgency": self.urgency,
            "cssClass": _URGENCY_CSS.get(self.urgency, "pro-gate-medium"),
        }

    def to_bot_config(self) -> dict | None:
        if not self.is_locked:
            return None
        emoji = _URGENCY_EMOJI.get(self.urgency, "📈")
        return {
            "locked_message": f"{emoji} {self.upgrade_reason} (Pro Only)",
            "cta_text": "Upgrade to Pro for full access",
            "upgrade_link": "/upgrade-from-discord",
        }


@dataclass
class CardDetailResponse:
    card_name: str
    external_id: str
    current_price: Decimal | None
    price_history: list
    sample_size: int
    match_confidence_avg: Decimal | None
    data_age: str
    source_breakdown: dict[str, int]
    access_tier: str
    pro_gate_config: ProGateConfig | None


@dataclass
class SignalsResponse:
    signals: list
    total_eligible: int
    access_tier: str
    pro_gate_config: ProGateConfig | None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd c:/Flashcard-planet
python -m pytest tests/test_response_types.py -v
```

Expected: all 8 tests PASS

- [ ] **Step 5: Commit**

```bash
cd c:/Flashcard-planet
git add backend/app/core/response_types.py tests/test_response_types.py
git commit -m "feat: add ProGateConfig, CardDetailResponse, SignalsResponse dataclasses"
```

---

## Task 2: `permissions.py` — Add `get_pro_gate_config()`

**Files:**
- Modify: `backend/app/core/permissions.py`
- Modify: `tests/test_permissions.py`

- [ ] **Step 1: Write failing tests** (append to existing `tests/test_permissions.py`)

```python
# Append to tests/test_permissions.py
from backend.app.core.response_types import ProGateConfig


class TestGetProGateConfig:
    def test_pro_user_returns_unlocked(self):
        from backend.app.core.permissions import get_pro_gate_config
        result = get_pro_gate_config("price_history", "pro")
        assert result.is_locked is False

    def test_free_user_price_history_is_locked(self):
        from backend.app.core.permissions import get_pro_gate_config
        result = get_pro_gate_config("price_history", "free")
        assert result.is_locked is True
        assert result.urgency == "medium"
        assert "180" in result.feature_name or "History" in result.feature_name

    def test_free_user_signals_full_is_high_urgency(self):
        from backend.app.core.permissions import get_pro_gate_config
        result = get_pro_gate_config("signals_full", "free")
        assert result.is_locked is True
        assert result.urgency == "high"

    def test_free_user_source_comparison_is_low_urgency(self):
        from backend.app.core.permissions import get_pro_gate_config
        result = get_pro_gate_config("source_comparison", "free")
        assert result.is_locked is True
        assert result.urgency == "low"

    def test_unknown_feature_returns_generic_locked_config(self):
        from backend.app.core.permissions import get_pro_gate_config
        result = get_pro_gate_config("nonexistent_feature", "free")
        assert result.is_locked is True
        assert result.upgrade_reason  # non-empty
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd c:/Flashcard-planet
python -m pytest tests/test_permissions.py::TestGetProGateConfig -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'get_pro_gate_config'`

- [ ] **Step 3: Add `get_pro_gate_config()` to `permissions.py`**

Add at the bottom of `backend/app/core/permissions.py`, after the existing functions:

```python
from backend.app.core.response_types import ProGateConfig   # add at top of file


_PRO_GATE_STRATEGIES: dict[str, ProGateConfig] = {
    "price_history": ProGateConfig(
        is_locked=True,
        feature_name="Extended Price History (180 days)",
        upgrade_reason="See long-term price patterns",
        urgency="medium",
    ),
    "signals_full": ProGateConfig(
        is_locked=True,
        feature_name="Unlimited Signals + AI Explanation",
        upgrade_reason="Get all market signals",
        urgency="high",
    ),
    "source_comparison": ProGateConfig(
        is_locked=True,
        feature_name="Detailed eBay vs TCG Comparison",
        upgrade_reason="Compare all price sources",
        urgency="low",
    ),
}


def get_pro_gate_config(feature: str, access_tier: str) -> ProGateConfig:
    """Return ProGateConfig for feature+tier. Unlocked if Pro; locked with strategy if Free."""
    if access_tier.lower() == "pro":
        return ProGateConfig(is_locked=False)
    strategy = _PRO_GATE_STRATEGIES.get(feature)
    if strategy is None:
        return ProGateConfig(is_locked=True, upgrade_reason="Upgrade to Pro for full access")
    return strategy
```

Also add the import at the top of `permissions.py`:
```python
from __future__ import annotations
```
(already present — just add the `ProGateConfig` import after the existing imports)

- [ ] **Step 4: Run all permission tests**

```bash
cd c:/Flashcard-planet
python -m pytest tests/test_permissions.py -v
```

Expected: all tests PASS (including existing + new `TestGetProGateConfig`)

- [ ] **Step 5: Commit**

```bash
cd c:/Flashcard-planet
git add backend/app/core/permissions.py tests/test_permissions.py
git commit -m "feat: add get_pro_gate_config() to permissions"
```

---

## Task 3: `core/data_service.py`

**Files:**
- Create: `backend/app/core/data_service.py`
- Create: `tests/test_data_service.py`

The `DataService` wraps two existing service functions:
- `card_detail_service.build_card_detail(db, asset_id, access_tier=...)` → returns `CardDetailViewModel | None`
- `signals_feed_service.build_signals_feed(db, access_tier, label_filter=None)` → returns `SignalsFeedResult`

`CardDetailViewModel` fields used: `.name`, `.external_id` (use `asset.external_id` from DB), `.current_price` (latest price), `.price_history`, `.sample_size`, `.match_confidence_avg`, `.data_age`, `.source_breakdown`.

Check exact fields available on `CardDetailViewModel`:

```bash
grep -n "^@dataclass\|^class CardDetail\|    [a-z].*:.*$" backend/app/services/card_detail_service.py | head -30
```

- [ ] **Step 1: Inspect `CardDetailViewModel` fields before writing tests**

```bash
cd c:/Flashcard-planet
sed -n '/^class CardDetailViewModel/,/^def /p' backend/app/services/card_detail_service.py | head -40
```

Note the exact field names. Adjust test field names in Step 2 if they differ from: `name`, `external_id`, `current_price`, `sample_size`, `match_confidence_avg`, `data_age`, `source_breakdown`.

- [ ] **Step 2: Write failing tests for DataService**

```python
# tests/test_data_service.py
from unittest.mock import MagicMock, patch
import uuid
from decimal import Decimal

import pytest

from backend.app.core.data_service import DataService
from backend.app.core.response_types import CardDetailResponse, SignalsResponse


def _mock_card_detail_vm():
    vm = MagicMock()
    vm.name = "Charizard Base Set"
    vm.latest_price = Decimal("150.00")    # CardDetailViewModel uses latest_price
    vm.price_history = []
    vm.sample_size = 47
    vm.match_confidence_avg = Decimal("0.85")
    vm.data_age = None
    vm.source_breakdown = {"eBay": 33, "TCG": 14}
    return vm


def _mock_signals_feed_result():
    result = MagicMock()
    result.rows = []
    result.hidden_count = 12    # SignalsFeedResult uses hidden_count, not total_eligible
    return result


class TestDataServiceGetCardDetail:
    @patch("backend.app.core.data_service.build_card_detail")
    def test_returns_card_detail_response_for_known_asset(self, mock_build):
        mock_build.return_value = _mock_card_detail_vm()
        db = MagicMock()
        asset_id = uuid.uuid4()

        result = DataService.get_card_detail(db, asset_id, access_tier="free")

        assert isinstance(result, CardDetailResponse)
        assert result.card_name == "Charizard Base Set"
        assert result.sample_size == 47
        assert result.access_tier == "free"

    @patch("backend.app.core.data_service.build_card_detail")
    def test_returns_none_for_unknown_asset(self, mock_build):
        mock_build.return_value = None
        db = MagicMock()
        result = DataService.get_card_detail(db, uuid.uuid4(), access_tier="free")
        assert result is None

    @patch("backend.app.core.data_service.build_card_detail")
    def test_free_user_gets_pro_gate_config_for_price_history(self, mock_build):
        mock_build.return_value = _mock_card_detail_vm()
        db = MagicMock()
        result = DataService.get_card_detail(db, uuid.uuid4(), access_tier="free")
        assert result.pro_gate_config is not None
        assert result.pro_gate_config.is_locked is True

    @patch("backend.app.core.data_service.build_card_detail")
    def test_pro_user_gets_no_pro_gate(self, mock_build):
        mock_build.return_value = _mock_card_detail_vm()
        db = MagicMock()
        result = DataService.get_card_detail(db, uuid.uuid4(), access_tier="pro")
        assert result.pro_gate_config is None


class TestDataServiceGetSignals:
    @patch("backend.app.core.data_service.build_signals_feed")
    def test_returns_signals_response(self, mock_feed):
        mock_feed.return_value = _mock_signals_feed_result()
        db = MagicMock()
        result = DataService.get_signals(db, access_tier="free")
        assert isinstance(result, SignalsResponse)
        assert result.total_eligible == 12
        assert result.access_tier == "free"

    @patch("backend.app.core.data_service.build_signals_feed")
    def test_free_user_gets_signals_pro_gate(self, mock_feed):
        mock_feed.return_value = _mock_signals_feed_result()
        db = MagicMock()
        result = DataService.get_signals(db, access_tier="free")
        assert result.pro_gate_config is not None
        assert result.pro_gate_config.urgency == "high"

    @patch("backend.app.core.data_service.build_signals_feed")
    def test_pro_user_gets_no_signals_gate(self, mock_feed):
        mock_feed.return_value = _mock_signals_feed_result()
        db = MagicMock()
        result = DataService.get_signals(db, access_tier="pro")
        assert result.pro_gate_config is None
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd c:/Flashcard-planet
python -m pytest tests/test_data_service.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'DataService'`

- [ ] **Step 4: Implement `data_service.py`**

First confirm `CardDetailViewModel` field names:
```bash
sed -n '/^class CardDetailViewModel/,/^def /p' c:/Flashcard-planet/backend/app/services/card_detail_service.py | head -30
```

Then write:

```python
# backend/app/core/data_service.py
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.core.permissions import get_pro_gate_config
from backend.app.core.response_types import CardDetailResponse, ProGateConfig, SignalsResponse
from backend.app.services.card_detail_service import build_card_detail
from backend.app.services.signals_feed_service import build_signals_feed


def _format_data_age(dt: datetime | None) -> str:
    if dt is None:
        return "Unknown"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    hours = int(delta.total_seconds() // 3600)
    if hours < 1:
        return "Updated less than 1 hour ago"
    if hours == 1:
        return "Updated 1 hour ago"
    if hours < 24:
        return f"Updated {hours} hours ago"
    days = hours // 24
    return f"Updated {days} day{'s' if days != 1 else ''} ago"


class DataService:
    @staticmethod
    def get_card_detail(
        db: Session,
        asset_id: uuid.UUID,
        *,
        access_tier: str,
        external_id: str = "",
    ) -> CardDetailResponse | None:
        vm = build_card_detail(db, asset_id, access_tier=access_tier)
        if vm is None:
            return None

        gate = (
            get_pro_gate_config("price_history", access_tier)
            if access_tier.lower() != "pro"
            else None
        )

        return CardDetailResponse(
            card_name=vm.name,
            external_id=external_id,        # passed in by caller (from Asset.external_id)
            current_price=vm.latest_price,  # CardDetailViewModel uses latest_price, not current_price
            price_history=vm.price_history,
            sample_size=vm.sample_size,
            match_confidence_avg=vm.match_confidence_avg,
            data_age=_format_data_age(vm.data_age),
            source_breakdown=vm.source_breakdown,
            access_tier=access_tier,
            pro_gate_config=gate,
        )

    @staticmethod
    def get_signals(
        db: Session,
        *,
        access_tier: str,
        label_filter: str | None = None,
    ) -> SignalsResponse:
        result = build_signals_feed(db, access_tier, label_filter=label_filter)

        gate = (
            get_pro_gate_config("signals_full", access_tier)
            if access_tier.lower() != "pro"
            else None
        )

        return SignalsResponse(
            signals=result.rows,
            total_eligible=len(result.rows) + result.hidden_count,  # SignalsFeedResult has no .total_eligible
            access_tier=access_tier,
            pro_gate_config=gate,
        )
```

**Note:** `CardDetailViewModel` uses `vm.data_age` (a `datetime | None`), `vm.name`, `vm.external_id`, `vm.current_price`, `vm.sample_size`, `vm.match_confidence_avg`, `vm.source_breakdown`, `vm.price_history`. If actual field names differ (check step 1 output), update accordingly.

**Note on `SignalsFeedResult`:** `build_signals_feed` returns a `SignalsFeedResult`. Check its fields:
```bash
grep -A 10 "class SignalsFeedResult" backend/app/services/signals_feed_service.py
```
Adjust `result.rows` and `result.total_eligible` to match actual field names.

- [ ] **Step 5: Run tests**

```bash
cd c:/Flashcard-planet
python -m pytest tests/test_data_service.py -v
```

Expected: all 7 tests PASS

- [ ] **Step 6: Commit**

```bash
cd c:/Flashcard-planet
git add backend/app/core/data_service.py tests/test_data_service.py
git commit -m "feat: add DataService wrapping card_detail and signals_feed services"
```

---

## Task 4: New API Endpoint `/api/v1/cards/{external_id}/enriched`

This endpoint lets the Discord Bot fetch enriched card data (with ProGateConfig) over HTTP. The Bot's `BackendClient` gains a new method to call it.

**Files:**
- Create: `backend/app/api/routes/cards.py`
- Modify: `backend/app/api/router.py`
- Modify: `bot/api_client.py`
- Create: `tests/test_cards_enriched_api.py`

- [ ] **Step 1: Check how other routes get user + DB**

```bash
cd c:/Flashcard-planet
head -60 backend/app/api/routes/alerts.py
```

Look for how `db: Session = Depends(get_db)` and user/discord_user_id are retrieved. The Bot passes `discord_user_id` as a query param or path param. Use the same pattern.

- [ ] **Step 2: Check existing router registration**

```bash
cat backend/app/api/router.py
```

Note the import pattern and `include_router` calls. You'll add one more.

- [ ] **Step 3: Write failing integration tests**

```python
# tests/test_cards_enriched_api.py
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


class TestCardsEnrichedEndpoint:
    @patch("backend.app.api.routes.cards.DataService.get_card_detail")
    @patch("backend.app.api.routes.cards._resolve_asset_id")
    def test_returns_enriched_data_for_known_card(self, mock_resolve, mock_ds, client):
        asset_id = uuid.uuid4()
        mock_resolve.return_value = asset_id

        from backend.app.core.response_types import CardDetailResponse, ProGateConfig
        mock_ds.return_value = CardDetailResponse(
            card_name="Charizard Base Set",
            external_id="base1-4",
            current_price=Decimal("150.00"),
            price_history=[],
            sample_size=47,
            match_confidence_avg=Decimal("0.85"),
            data_age="Updated 3 hours ago",
            source_breakdown={"eBay": 70, "TCG": 30},
            access_tier="free",
            pro_gate_config=ProGateConfig(
                is_locked=True,
                feature_name="Extended Price History (180 days)",
                upgrade_reason="See long-term price patterns",
                urgency="medium",
            ),
        )

        response = client.get("/api/v1/cards/base1-4/enriched?discord_user_id=123")
        assert response.status_code == 200
        data = response.json()
        assert data["card_name"] == "Charizard Base Set"
        assert data["sample_size"] == 47
        assert data["pro_gate"]["is_locked"] is True
        assert data["pro_gate"]["urgency"] == "medium"

    @patch("backend.app.api.routes.cards._resolve_asset_id")
    def test_returns_404_for_unknown_card(self, mock_resolve, client):
        mock_resolve.return_value = None
        response = client.get("/api/v1/cards/unknown-card/enriched?discord_user_id=123")
        assert response.status_code == 404

    @patch("backend.app.api.routes.cards.DataService.get_card_detail")
    @patch("backend.app.api.routes.cards._resolve_asset_id")
    def test_pro_user_gets_no_pro_gate(self, mock_resolve, mock_ds, client):
        mock_resolve.return_value = uuid.uuid4()
        from backend.app.core.response_types import CardDetailResponse
        mock_ds.return_value = CardDetailResponse(
            card_name="Test Card",
            external_id="test-1",
            current_price=Decimal("10.00"),
            price_history=[],
            sample_size=10,
            match_confidence_avg=None,
            data_age="Updated 1 hour ago",
            source_breakdown={},
            access_tier="pro",
            pro_gate_config=None,
        )
        response = client.get("/api/v1/cards/test-1/enriched?discord_user_id=456")
        assert response.status_code == 200
        assert response.json()["pro_gate"] is None
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
cd c:/Flashcard-planet
python -m pytest tests/test_cards_enriched_api.py -v 2>&1 | head -20
```

Expected: import errors or 404s on the new route

- [ ] **Step 5: Check how `discord_user_id` maps to `access_tier` in existing routes**

```bash
grep -n "discord_user_id\|access_tier\|User\|user_service" backend/app/api/routes/alerts.py | head -20
```

This tells you how to look up a user's tier from their Discord ID.

- [ ] **Step 6: Check `user_service` for Discord lookup**

```bash
grep -n "def.*discord\|discord_user_id" backend/app/services/user_service.py | head -10
```

Note the function name for getting a user by Discord ID.

- [ ] **Step 7: Check how asset is looked up by external_id**

```bash
grep -n "external_id\|def.*asset\|def.*card" backend/app/services/price_service.py | head -20
```

Look for `get_asset_price_by_external_id` or similar — you'll use the Asset lookup to get `asset.id`.

- [ ] **Step 8: Implement `backend/app/api/routes/cards.py`**

```python
# backend/app/api/routes/cards.py
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.core.data_service import DataService
from backend.app.db.session import get_db
from backend.app.models.asset import Asset  # adjust import if needed
from backend.app.services import user_service  # adjust if needed

router = APIRouter(prefix="/cards", tags=["cards"])


def _resolve_asset_id(db: Session, external_id: str) -> uuid.UUID | None:
    """Look up asset UUID from external_id string."""
    asset = db.query(Asset).filter(Asset.external_id == external_id).first()
    return asset.id if asset else None


def _get_access_tier(db: Session, discord_user_id: str | None) -> str:
    if not discord_user_id:
        return "free"
    # Use existing user_service lookup — adjust function name per Step 6
    user = user_service.get_user_by_discord_id(db, discord_user_id)
    return user.access_tier if user else "free"


@router.get("/{external_id}/enriched")
def get_card_enriched(
    external_id: str,
    discord_user_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    asset_id = _resolve_asset_id(db, external_id)
    if asset_id is None:
        raise HTTPException(status_code=404, detail="Card not found")

    access_tier = _get_access_tier(db, discord_user_id)
    response = DataService.get_card_detail(db, asset_id, access_tier=access_tier, external_id=external_id)
    if response is None:
        raise HTTPException(status_code=404, detail="Card not found")

    gate = None
    if response.pro_gate_config:
        gate = response.pro_gate_config.to_web_config()

    return {
        "card_name": response.card_name,
        "external_id": response.external_id,
        "current_price": str(response.current_price) if response.current_price else None,
        "sample_size": response.sample_size,
        "match_confidence_avg": str(response.match_confidence_avg) if response.match_confidence_avg else None,
        "data_age": response.data_age,
        "source_breakdown": response.source_breakdown,
        "access_tier": response.access_tier,
        "pro_gate": gate,
    }
```

**Note:** Adjust `user_service.get_user_by_discord_id` to the actual function name found in Step 6. Adjust `Asset` model import path.

- [ ] **Step 9: Register router in `router.py`**

Open `backend/app/api/router.py` and add:

```python
from backend.app.api.routes.cards import router as cards_router

# Inside the router setup, alongside other include_router calls:
api_router.include_router(cards_router)
```

- [ ] **Step 10: Run tests**

```bash
cd c:/Flashcard-planet
python -m pytest tests/test_cards_enriched_api.py -v
```

Expected: all 3 tests PASS

- [ ] **Step 11: Run full test suite to check for regressions**

```bash
cd c:/Flashcard-planet
python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: all previously passing tests still PASS

- [ ] **Step 12: Add `fetch_card_detail_enriched()` to `bot/api_client.py`**

```python
# In bot/api_client.py, add this method to BackendClient:

async def fetch_card_detail_enriched(
    self, external_id: str, discord_user_id: str
) -> dict | None:
    async with httpx.AsyncClient(timeout=10.0) as http:
        response = await http.get(
            f"{self.base_url}/api/v1/cards/{external_id}/enriched",
            params={"discord_user_id": discord_user_id},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
```

- [ ] **Step 13: Commit**

```bash
cd c:/Flashcard-planet
git add backend/app/api/routes/cards.py backend/app/api/router.py bot/api_client.py tests/test_cards_enriched_api.py
git commit -m "feat: add /api/v1/cards/{id}/enriched endpoint and BackendClient method"
```

---

## Task 5: `core/boundary_check.py` (CI Documentation)

**Files:**
- Create: `backend/app/core/boundary_check.py`

No test needed — this is a rules dict + documentation. It will be wired into CI separately.

- [ ] **Step 1: Create `boundary_check.py`**

```python
# backend/app/core/boundary_check.py
"""
Boundary rules for the DataService layer.

New Bot code and new Web route code MUST NOT import from services/ or models/
directly. All data access goes through DataService.

Whitelist exceptions (safe to import anywhere):
  - core.permissions
  - core.response_types
  - core.config
  - core.data_service (the gateway itself)

To enforce in CI, scan new .py files for forbidden patterns:
  grep -rn "from backend.app.services\|from backend.app.models" bot/ \
    | grep -v "# boundary-ok"

Add `# boundary-ok` comment on any intentional exception.
"""

BOUNDARY_RULES = {
    "forbidden_direct_imports": [
        "backend.app.models",
        "backend.app.services",
    ],
    "must_go_through": [
        "backend.app.core.data_service.DataService",
    ],
    "whitelist": [
        "backend.app.core.permissions",
        "backend.app.core.response_types",
        "backend.app.core.config",
        "backend.app.core.data_service",
    ],
    "boundary_ok_marker": "# boundary-ok",
}
```

- [ ] **Step 2: Commit**

```bash
cd c:/Flashcard-planet
git add backend/app/core/boundary_check.py
git commit -m "docs: add boundary_check rules for DataService layer"
```

---

## Phase A Complete — Verification

- [ ] **Run full test suite**

```bash
cd c:/Flashcard-planet
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all tests PASS, no regressions

- [ ] **Smoke test the new endpoint manually**

Start the backend:
```bash
cd c:/Flashcard-planet
uvicorn backend.app.main:app --reload --port 8000
```

In another terminal:
```bash
curl "http://localhost:8000/api/v1/cards/base1-4/enriched?discord_user_id=test123"
```

Expected: JSON response with `card_name`, `sample_size`, `pro_gate` fields (or 404 if card doesn't exist in dev DB — that's fine)

- [ ] **Confirm site.py still serves normally**

```bash
curl -s http://localhost:8000/ | grep -i "flashcard\|title" | head -3
```

Expected: HTML with page title — confirms existing routes untouched

---

## Phase A → Phase B Handoff

Phase A is complete when:
- `DataService.get_card_detail()` and `get_signals()` return typed responses
- `/api/v1/cards/{id}/enriched` is live and tested
- `BackendClient.fetch_card_detail_enriched()` is available for Phase C
- All existing tests pass

Phase B plan: `docs/superpowers/plans/2026-04-17-phase-b-web-features.md` (to be written)
Phase C plan: `docs/superpowers/plans/2026-04-17-phase-c-discord-funnel.md` (to be written after Phase B)
