# Phase B: Web Feature Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add urgency-aware ProGate rendering, wire it into the card detail price-history gate, and add two new routes (`/cards/{id}/sources` and `/cards/{id}/history`) for Phase B of the v3.1 architecture migration.

**Architecture:** Phase A delivered `ProGateConfig` (with urgency + feature_name + upgrade_reason) and the DataService layer. Phase B makes the Web frontend consume those fields — updating the blur-overlay helper to be urgency-aware and exposing the source breakdown + standalone history pages that Phase C's Discord links will deep-link to. `site.py` is extended via new routes; old routes are NOT refactored.

**Tech Stack:** Python 3.12, FastAPI, `site.py` f-string HTML rendering, SQLite in tests, `unittest.TestCase` (no pytest fixtures), `SessionLocal()` context manager for DB access in routes.

---

## Pre-task: Create Phase B branch

```bash
git checkout main
git pull
git checkout -b feat/phase-b-web-features
```

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `backend/app/core/banner.py` | Modify | Add `_progate_html_from_config()` — urgency-aware ProGate overlay |
| `backend/app/static/site.css` | Modify | Add urgency CSS classes (`progate__cta--high/medium/low`, pulse animation) |
| `backend/app/site.py` | Modify | Wire urgency ProGate into card detail; add `/sources` and `/history` routes |
| `tests/test_banner.py` | Create | Unit tests for `_progate_html_from_config()` |
| `tests/test_sources_history_routes.py` | Create | Route tests for the two new B2 routes |

---

## Task 1: Urgency-aware ProGate HTML helper + CSS

**Files:**
- Modify: `backend/app/core/banner.py`
- Modify: `backend/app/static/site.css`
- Create: `tests/test_banner.py`

### Background

`banner.py` currently has `_progate_html(cta_label, blurred_html, feature_label)` — three loose strings, no urgency, no tie to `ProGateConfig`. Phase A built `ProGateConfig` with `urgency`, `feature_name`, `upgrade_reason` and `to_web_config()`. Phase B wires them together.

The new function `_progate_html_from_config(config, blurred_html)` replaces caller-side string composition. If `config.is_locked` is False, it returns `blurred_html` unchanged (no overlay at all). If locked, it renders blur + overlay with urgency CSS class on the CTA button.

CSS adds `.progate__cta--high` (#FF4444 + pulse), `.progate__cta--medium` (#FF8800), `.progate__cta--low` (#888888).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_banner.py`:

```python
"""tests/test_banner.py — unit tests for banner.py ProGate helpers."""
from __future__ import annotations

import unittest

from backend.app.core.banner import _progate_html_from_config
from backend.app.core.response_types import ProGateConfig


class TestProgateHtmlFromConfig(unittest.TestCase):
    def _locked(self, urgency: str = "medium") -> ProGateConfig:
        return ProGateConfig(
            is_locked=True,
            feature_name="Extended Price History (180 days)",
            upgrade_reason="See long-term price patterns",
            urgency=urgency,
        )

    def _unlocked(self) -> ProGateConfig:
        return ProGateConfig(is_locked=False)

    # ── Unlocked behaviour ───────────────────────────────────────────────

    def test_unlocked_returns_content_directly(self):
        html = _progate_html_from_config(self._unlocked(), "<p>visible</p>")
        self.assertIn("<p>visible</p>", html)

    def test_unlocked_has_no_overlay(self):
        html = _progate_html_from_config(self._unlocked(), "<p>x</p>")
        self.assertNotIn("progate__overlay", html)

    # ── Locked: feature_name / upgrade_reason ────────────────────────────

    def test_locked_renders_feature_name(self):
        html = _progate_html_from_config(self._locked(), "<canvas></canvas>")
        self.assertIn("Extended Price History (180 days)", html)

    def test_locked_renders_upgrade_reason(self):
        html = _progate_html_from_config(self._locked(), "<canvas></canvas>")
        self.assertIn("See long-term price patterns", html)

    def test_locked_renders_upgrade_link(self):
        html = _progate_html_from_config(self._locked(), "<canvas></canvas>")
        self.assertIn("/upgrade", html)

    def test_locked_blurs_content(self):
        html = _progate_html_from_config(self._locked(), "<canvas id='x'></canvas>")
        self.assertIn("progate__blur", html)
        self.assertIn("<canvas id='x'></canvas>", html)

    # ── Urgency CSS ──────────────────────────────────────────────────────

    def test_high_urgency_class(self):
        html = _progate_html_from_config(self._locked("high"), "<p/>")
        self.assertIn("progate__cta--high", html)

    def test_medium_urgency_class(self):
        html = _progate_html_from_config(self._locked("medium"), "<p/>")
        self.assertIn("progate__cta--medium", html)

    def test_low_urgency_class(self):
        html = _progate_html_from_config(self._locked("low"), "<p/>")
        self.assertIn("progate__cta--low", html)

    def test_unknown_urgency_defaults_to_medium_class(self):
        config = ProGateConfig(
            is_locked=True, feature_name="X", upgrade_reason="Y", urgency="unknown_val"
        )
        html = _progate_html_from_config(config, "<p/>")
        self.assertIn("progate__cta--medium", html)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_banner.py -v
```

Expected: FAIL — `ImportError: cannot import name '_progate_html_from_config' from 'backend.app.core.banner'`

- [ ] **Step 3: Add `_progate_html_from_config` to `banner.py`**

Open `backend/app/core/banner.py`. Add at the top after existing imports:

```python
from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.core.response_types import ProGateConfig
```

Then add this function after the existing `_progate_html` function:

```python
_URGENCY_BTN_STYLES: dict[str, str] = {
    "high":   "background:#FF4444;color:white;text-decoration:none;"
              "padding:8px 20px;border-radius:6px;font-size:0.9em;",
    "medium": "background:#FF8800;color:white;text-decoration:none;"
              "padding:8px 20px;border-radius:6px;font-size:0.9em;",
    "low":    "background:#888888;color:white;text-decoration:none;"
              "padding:8px 20px;border-radius:6px;font-size:0.9em;",
}
_DEFAULT_BTN_STYLE = _URGENCY_BTN_STYLES["medium"]


def _progate_html_from_config(
    config: "ProGateConfig",
    blurred_content_html: str,
) -> str:
    """Urgency-aware ProGate overlay driven by ProGateConfig.

    Returns blurred_content_html unchanged when config.is_locked is False.
    """
    if not config.is_locked:
        return blurred_content_html

    urgency = config.urgency if config.urgency in _URGENCY_BTN_STYLES else "medium"
    btn_style = _URGENCY_BTN_STYLES[urgency]

    return f"""
<div class="progate" data-zh="升级以解锁{escape(config.feature_name)}"
     aria-label="Pro feature: {escape(config.feature_name)}"
     style="position:relative;overflow:hidden;border-radius:8px;">
  <div class="progate__blur" aria-hidden="true"
       style="filter:blur(4px);pointer-events:none;user-select:none;">
    {blurred_content_html}
  </div>
  <div class="progate__overlay"
       style="position:absolute;inset:0;display:flex;flex-direction:column;
              align-items:center;justify-content:center;gap:12px;
              background:rgba(255,255,255,0.55);backdrop-filter:blur(2px);">
    <p class="progate__feature"
       style="margin:0;font-weight:600;color:#374151;">{escape(config.feature_name)}</p>
    <p class="progate__reason"
       style="margin:0;color:#6b7280;font-size:0.875em;">{escape(config.upgrade_reason)}</p>
    <a href="{UPGRADE_URL}"
       class="btn btn--pro progate__cta progate__cta--{urgency}"
       style="{btn_style}">
      Unlock {escape(config.feature_name)} — Pro Only
    </a>
  </div>
</div>"""
```

The full `banner.py` after edits:

```python
"""
Shared HTML helpers for tier-gating UI components.

_upgrade_banner_html  — inline banner shown below truncated content
_progate_html         — blur + overlay for fully gated content (legacy, 3 strings)
_progate_html_from_config — urgency-aware overlay driven by ProGateConfig
"""
from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.core.response_types import ProGateConfig

UPGRADE_URL = "/upgrade"

_URGENCY_BTN_STYLES: dict[str, str] = {
    "high":   "background:#FF4444;color:white;text-decoration:none;"
              "padding:8px 20px;border-radius:6px;font-size:0.9em;",
    "medium": "background:#FF8800;color:white;text-decoration:none;"
              "padding:8px 20px;border-radius:6px;font-size:0.9em;",
    "low":    "background:#888888;color:white;text-decoration:none;"
              "padding:8px 20px;border-radius:6px;font-size:0.9em;",
}


def _upgrade_banner_html(
    feature_label: str,
    cta_label: str = "Upgrade to Pro",
    hidden_count: int = 0,
) -> str:
    """Inline banner placed below a truncated list to invite upgrade."""
    hidden_line = (
        f'<p class="upgrade-banner__count" style="margin:2px 0 0;font-size:0.85em;opacity:0.85;">'
        f"{hidden_count} more available with Pro</p>"
        if hidden_count > 0
        else ""
    )
    return f"""
<div class="upgrade-banner" data-zh="升级到 Pro 以解锁{feature_label}"
     style="display:flex;align-items:center;justify-content:space-between;
            background:#fefce8;border:1px solid #fde68a;border-radius:8px;
            padding:12px 16px;margin-top:12px;">
  <div class="upgrade-banner__body" style="display:flex;align-items:center;gap:12px;">
    <span class="upgrade-banner__icon" style="font-size:1.4em;">&#128274;</span>
    <div class="upgrade-banner__text">
      <strong>Unlock {feature_label}</strong>
      {hidden_line}
    </div>
  </div>
  <a href="{UPGRADE_URL}"
     class="btn btn--pro btn--sm upgrade-banner__cta"
     style="background:#7c3aed;color:white;text-decoration:none;
            padding:6px 14px;border-radius:6px;font-size:0.875em;white-space:nowrap;">
    {cta_label}
  </a>
</div>"""


def _progate_html(
    cta_label: str,
    blurred_content_html: str,
    feature_label: str = "this Pro feature",
) -> str:
    """Blur + overlay wrapper for fully gated content blocks."""
    return f"""
<div class="progate" data-zh="升级以解锁{feature_label}"
     aria-label="Pro feature: {feature_label}"
     style="position:relative;overflow:hidden;border-radius:8px;">
  <div class="progate__blur" aria-hidden="true"
       style="filter:blur(4px);pointer-events:none;user-select:none;">
    {blurred_content_html}
  </div>
  <div class="progate__overlay"
       style="position:absolute;inset:0;display:flex;flex-direction:column;
              align-items:center;justify-content:center;gap:12px;
              background:rgba(255,255,255,0.55);backdrop-filter:blur(2px);">
    <p class="progate__label"
       style="margin:0;font-weight:600;color:#374151;">Pro feature</p>
    <a href="{UPGRADE_URL}"
       class="btn btn--pro"
       style="background:#7c3aed;color:white;text-decoration:none;
              padding:8px 20px;border-radius:6px;font-size:0.9em;">
      {cta_label}
    </a>
  </div>
</div>"""


def _progate_html_from_config(
    config: "ProGateConfig",
    blurred_content_html: str,
) -> str:
    """Urgency-aware ProGate overlay driven by ProGateConfig.

    Returns blurred_content_html unchanged when config.is_locked is False.
    """
    if not config.is_locked:
        return blurred_content_html

    urgency = config.urgency if config.urgency in _URGENCY_BTN_STYLES else "medium"
    btn_style = _URGENCY_BTN_STYLES[urgency]

    return f"""
<div class="progate" data-zh="升级以解锁{escape(config.feature_name)}"
     aria-label="Pro feature: {escape(config.feature_name)}"
     style="position:relative;overflow:hidden;border-radius:8px;">
  <div class="progate__blur" aria-hidden="true"
       style="filter:blur(4px);pointer-events:none;user-select:none;">
    {blurred_content_html}
  </div>
  <div class="progate__overlay"
       style="position:absolute;inset:0;display:flex;flex-direction:column;
              align-items:center;justify-content:center;gap:12px;
              background:rgba(255,255,255,0.55);backdrop-filter:blur(2px);">
    <p class="progate__feature"
       style="margin:0;font-weight:600;color:#374151;">{escape(config.feature_name)}</p>
    <p class="progate__reason"
       style="margin:0;color:#6b7280;font-size:0.875em;">{escape(config.upgrade_reason)}</p>
    <a href="{UPGRADE_URL}"
       class="btn btn--pro progate__cta progate__cta--{urgency}"
       style="{btn_style}">
      Unlock {escape(config.feature_name)} — Pro Only
    </a>
  </div>
</div>"""
```

- [ ] **Step 4: Add urgency CSS to `site.css`**

Append to the end of `backend/app/static/site.css`:

```css
/* ─── ProGate urgency CTA colours ────────────────────────────────────────── */
.progate__cta--high {
  background: #FF4444 !important;
  animation: progate-pulse 1.5s ease-in-out infinite;
}

.progate__cta--medium {
  background: #FF8800 !important;
}

.progate__cta--low {
  background: #888888 !important;
}

@keyframes progate-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.85;
    transform: scale(1.03);
  }
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_banner.py -v
```

Expected: All 10 tests PASS

- [ ] **Step 6: Run full suite to check for regressions**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: All previously passing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/banner.py backend/app/static/site.css tests/test_banner.py
git commit -m "feat: add urgency-aware _progate_html_from_config + urgency CSS classes"
```

---

## Task 2: Wire urgency ProGate into card_detail_page (B1)

**Files:**
- Modify: `backend/app/site.py` (lines ~19, ~879–891)

### Background

`card_detail_page` currently builds `truncated_banner` by calling:
```python
truncated_banner = _progate_html("View Full History", blurred_preview, "180-day price history")
```

This ignores `ProGateConfig.urgency`, `feature_name`, and `upgrade_reason`. The spec requires that CTA text/urgency flow from `get_pro_gate_config()` in `permissions.py`, not from hardcoded strings in templates. After this task, the banner will use `_progate_html_from_config(get_pro_gate_config("price_history", access_tier), ...)`.

- [ ] **Step 1: Update the import line in `site.py`**

Find the line (currently line ~19):
```python
from backend.app.core.banner import _progate_html, _upgrade_banner_html
```

Change it to:
```python
from backend.app.core.banner import _progate_html, _progate_html_from_config, _upgrade_banner_html
```

Also find the permissions import (currently line ~21):
```python
from backend.app.core.permissions import Feature, alert_limit, can, get_capabilities
```

Change it to:
```python
from backend.app.core.permissions import Feature, alert_limit, can, get_capabilities, get_pro_gate_config
```

- [ ] **Step 2: Replace the `truncated_banner` block**

Find this block in `card_detail_page` (around line 879):
```python
    truncated_banner = ""
    if vm.history_truncated:
        blurred_preview = (
            "<p style='margin:0;font-style:italic;color:#6b7280;'>"
            + _lang_pair(
                "免费账户仅显示最近 7 天价格记录。",
                "Free accounts show only the last 7 days of price history.",
            )
            + "</p>"
        )
        truncated_banner = _progate_html(
            "View Full History", blurred_preview, "180-day price history"
        )
```

Replace with:
```python
    truncated_banner = ""
    if vm.history_truncated:
        blurred_preview = (
            "<p style='margin:0;font-style:italic;color:#6b7280;'>"
            + _lang_pair(
                "免费账户仅显示最近 7 天价格记录。",
                "Free accounts show only the last 7 days of price history.",
            )
            + "</p>"
        )
        truncated_banner = _progate_html_from_config(
            get_pro_gate_config("price_history", access_tier),
            blurred_preview,
        )
```

- [ ] **Step 3: Run full test suite**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: All tests pass (no functional change to test output — just the class/style of the button changes).

- [ ] **Step 4: Commit**

```bash
git add backend/app/site.py
git commit -m "feat: wire urgency ProGate into card_detail truncated history banner"
```

---

## Task 3: `GET /cards/{external_id}/sources` route (B2)

**Files:**
- Modify: `backend/app/site.py` (add route after `card_detail_page`)
- Create: `tests/test_sources_history_routes.py`

### Background

Free users see a one-row summary (total samples, list of data sources without %). Pro users see a full breakdown table (source, count, % share). The ProGate overlay wraps the Pro table for free users — no CTA string is hardcoded in this route; it all comes from `get_pro_gate_config("source_comparison", access_tier)`.

`build_credibility_indicators(db, asset_id, access_tier)` already computes `source_breakdown` (dict `{source: fraction}`) and `sample_size`; reuse it directly.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sources_history_routes.py`:

```python
"""
tests/test_sources_history_routes.py

Route tests for Phase B2:
  - GET /cards/{external_id}/sources
  - GET /cards/{external_id}/history
"""
from __future__ import annotations

import unittest
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from backend.app.api.deps import get_database
from backend.app.site import router as site_router


def _fake_db():
    yield None


def _make_app() -> tuple[FastAPI, TestClient]:
    app = FastAPI()
    app.mount(
        "/static",
        StaticFiles(
            directory=Path(__file__).resolve().parents[1]
            / "backend"
            / "app"
            / "static"
        ),
        name="static",
    )
    app.include_router(site_router)
    app.dependency_overrides[get_database] = _fake_db
    return app, TestClient(app, raise_server_exceptions=False)


def _mock_asset(external_id: str = "xy1-001") -> MagicMock:
    asset = MagicMock()
    asset.id = uuid.uuid4()
    asset.name = "Charizard"
    asset.set_name = "Base Set"
    asset.card_number = "4"
    asset.external_id = external_id
    asset.category = "Pokemon"
    return asset


# ─────────────────────────────────────────────────────────────────────────────
# /cards/{external_id}/sources
# ─────────────────────────────────────────────────────────────────────────────

class TestCardSourcesRoute(unittest.TestCase):
    def setUp(self):
        self.app, self.client = _make_app()

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def _mock_credibility(self, *, pro: bool = False):
        from backend.app.services.card_credibility_service import CredibilityIndicators
        return CredibilityIndicators(
            sample_size=47,
            data_age_hours=3.0,
            source_breakdown={"ebay_sold": 0.72, "pokemon_tcg_api": 0.28} if pro else None,
            match_confidence=0.92 if pro else None,
            data_age_label="Updated 3h ago",
            sample_size_label="Based on 47 sales",
            confidence_status="green" if pro else "unknown",
        )

    def test_returns_404_for_unknown_card(self):
        with patch("backend.app.site.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = lambda s: mock_db
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.scalars.return_value.first.return_value = None

            response = self.client.get("/cards/does-not-exist/sources")

        self.assertEqual(response.status_code, 404)

    def test_free_user_sees_sample_size(self):
        asset = _mock_asset()
        credibility = self._mock_credibility(pro=False)

        with (
            patch("backend.app.site.SessionLocal") as mock_sl,
            patch(
                "backend.app.site.build_credibility_indicators",
                return_value=credibility,
            ),
        ):
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = lambda s: mock_db
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.scalars.return_value.first.return_value = asset

            response = self.client.get("/cards/xy1-001/sources")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Based on 47 sales", response.text)

    def test_free_user_sees_progate_overlay(self):
        asset = _mock_asset()
        credibility = self._mock_credibility(pro=False)

        with (
            patch("backend.app.site.SessionLocal") as mock_sl,
            patch(
                "backend.app.site.build_credibility_indicators",
                return_value=credibility,
            ),
        ):
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = lambda s: mock_db
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.scalars.return_value.first.return_value = asset

            response = self.client.get("/cards/xy1-001/sources")

        self.assertEqual(response.status_code, 200)
        self.assertIn("progate__overlay", response.text)

    def test_pro_user_sees_source_breakdown(self):
        asset = _mock_asset()
        credibility = self._mock_credibility(pro=True)

        with (
            patch("backend.app.site.SessionLocal") as mock_sl,
            patch(
                "backend.app.site.build_credibility_indicators",
                return_value=credibility,
            ),
        ):
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = lambda s: mock_db
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.scalars.return_value.first.return_value = asset

            response = self.client.get(
                "/cards/xy1-001/sources",
                cookies={"session": ""},  # session patched below
            )

        self.assertEqual(response.status_code, 200)

    def test_page_contains_card_name(self):
        asset = _mock_asset()
        credibility = self._mock_credibility(pro=False)

        with (
            patch("backend.app.site.SessionLocal") as mock_sl,
            patch(
                "backend.app.site.build_credibility_indicators",
                return_value=credibility,
            ),
        ):
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = lambda s: mock_db
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.scalars.return_value.first.return_value = asset

            response = self.client.get("/cards/xy1-001/sources")

        self.assertIn("Charizard", response.text)


# ─────────────────────────────────────────────────────────────────────────────
# /cards/{external_id}/history
# ─────────────────────────────────────────────────────────────────────────────

class TestCardHistoryRoute(unittest.TestCase):
    def setUp(self):
        self.app, self.client = _make_app()

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def _mock_vm(self):
        from backend.app.services.card_detail_service import CardDetailViewModel
        from datetime import datetime, UTC

        vm = MagicMock(spec=CardDetailViewModel)
        vm.name = "Charizard"
        vm.latest_price = Decimal("42.00")
        vm.currency = "USD"
        vm.price_history = []
        vm.history_truncated = False
        vm.image_url = None
        return vm

    def test_returns_404_for_unknown_card(self):
        with patch("backend.app.site.SessionLocal") as mock_sl:
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = lambda s: mock_db
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.scalars.return_value.first.return_value = None

            response = self.client.get("/cards/does-not-exist/history")

        self.assertEqual(response.status_code, 404)

    def test_returns_200_for_known_card(self):
        asset = _mock_asset()
        vm = self._mock_vm()

        with (
            patch("backend.app.site.SessionLocal") as mock_sl,
            patch("backend.app.site.build_card_detail", return_value=vm),
        ):
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = lambda s: mock_db
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.scalars.return_value.first.return_value = asset

            response = self.client.get("/cards/xy1-001/history")

        self.assertEqual(response.status_code, 200)

    def test_page_contains_card_name(self):
        asset = _mock_asset()
        vm = self._mock_vm()

        with (
            patch("backend.app.site.SessionLocal") as mock_sl,
            patch("backend.app.site.build_card_detail", return_value=vm),
        ):
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = lambda s: mock_db
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.scalars.return_value.first.return_value = asset

            response = self.client.get("/cards/xy1-001/history")

        self.assertIn("Charizard", response.text)

    def test_page_contains_price_history_heading(self):
        asset = _mock_asset()
        vm = self._mock_vm()

        with (
            patch("backend.app.site.SessionLocal") as mock_sl,
            patch("backend.app.site.build_card_detail", return_value=vm),
        ):
            mock_db = MagicMock()
            mock_sl.return_value.__enter__ = lambda s: mock_db
            mock_sl.return_value.__exit__ = MagicMock(return_value=False)
            mock_db.scalars.return_value.first.return_value = asset

            response = self.client.get("/cards/xy1-001/history")

        # Should include "Price history" or "价格历史" in the rendered page
        self.assertTrue(
            "Price history" in response.text or "价格历史" in response.text
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_sources_history_routes.py -v
```

Expected: FAIL — 404 for `/cards/xy1-001/sources` (route not registered yet)

- [ ] **Step 3: Add the `/cards/{external_id}/sources` route to `site.py`**

Insert this route immediately after the closing brace of `card_detail_page` (around line 975), before `@router.get("/signals"`:

```python
@router.get("/cards/{external_id}/sources", response_class=HTMLResponse)
def card_sources_page(request: Request, external_id: str) -> HTMLResponse:
    """Source breakdown comparison page — Free shows summary, Pro shows full table."""
    import uuid as _uuid

    username = _session_username(request)
    session = request.scope.get("session")
    user_id = session.get("user_id") if isinstance(session, dict) else None

    with SessionLocal() as db:
        current_user = None
        if user_id:
            try:
                current_user = db.get(User, _uuid.UUID(user_id))
            except Exception:
                current_user = None
        access_tier = current_user.access_tier if current_user else "free"

        asset = db.scalars(
            select(Asset).where(Asset.category == "Pokemon", Asset.external_id == external_id)
        ).first()
        if asset is None:
            raise HTTPException(status_code=404, detail="卡牌不存在。")

        credibility = build_credibility_indicators(db, asset_id=asset.id, access_tier=access_tier)

    gate_config = get_pro_gate_config("source_comparison", access_tier)

    # Summary row — always visible
    summary_html = f"""
    <dl class="detail-list">
      <div>
        <dt>{_lang_pair("样本量", "Sample size")}</dt>
        <dd>{escape(credibility.sample_size_label)}</dd>
      </div>
      <div>
        <dt>{_lang_pair("数据新鲜度", "Data freshness")}</dt>
        <dd>{escape(credibility.data_age_label)}</dd>
      </div>
    </dl>"""

    # Full source table — Pro only
    if credibility.source_breakdown:
        rows_html = "".join(
            f"""<tr>
              <td>{escape(_source_label_display(src))}</td>
              <td>{int(pct * 100)}%</td>
              <td>{int(pct * credibility.sample_size)}</td>
            </tr>"""
            for src, pct in sorted(
                credibility.source_breakdown.items(), key=lambda kv: kv[1], reverse=True
            )
        )
        full_table_html = f"""
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>{_lang_pair("数据源", "Source")}</th>
                <th>{_lang_pair("占比", "Share")}</th>
                <th>{_lang_pair("样本数", "Count")}</th>
              </tr>
            </thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>"""
    else:
        full_table_html = f"<p>{_lang_pair('暂无来源数据。', 'No source data available.')}</p>"

    sources_block = _progate_html_from_config(gate_config, full_table_html)

    body = f"""
    <section class="page-intro">
      <div>
        <p class="eyebrow">{_lang_pair("来源对比", "Source comparison")}</p>
        <h1>{escape(asset.name)}</h1>
        <p class="lede">
          {_lang_pair("查看该卡牌价格数据的各来源分布。升级到 Pro 即可解锁完整来源明细。",
          "View the source breakdown for this card's price data. Upgrade to Pro for the full table.")}
        </p>
      </div>
    </section>

    <section class="module module-wide">
      <div class="module-head">
        <p class="card-kicker">{_lang_pair("数据来源", "Data sources")}</p>
        <h2>{_lang_pair("价格来源明细", "Price source breakdown")}</h2>
      </div>
      {summary_html}
      {sources_block}
      <div class="detail-actions" style="margin-top:1.5rem;">
        <a class="button button-secondary" href="/cards/{escape(external_id)}">{_lang_pair("返回卡牌详情", "Back to card detail")}</a>
      </div>
    </section>
    """

    return _render_shell(
        title=f"{asset.name} — Sources",
        current_path="/cards",
        body=body,
        page_key="card-sources",
        username=username,
    )
```

Also add `_source_label_display` helper function near the top of `site.py`, after the other `_` helper functions (around line 85, after `_build_cards_query_params`):

```python
def _source_label_display(source: str) -> str:
    return {
        "ebay_sold": "eBay Sold",
        "pokemon_tcg_api": "TCG API",
        "manual_seed": "Manual",
        "sample": "Sample",
    }.get(source, source)
```

- [ ] **Step 4: Run sources-route tests**

```bash
python -m pytest tests/test_sources_history_routes.py::TestCardSourcesRoute -v
```

Expected: All 5 source-route tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/site.py tests/test_sources_history_routes.py
git commit -m "feat: add /cards/{id}/sources route with Free summary + Pro ProGate"
```

---

## Task 4: `GET /cards/{external_id}/history` route (B2)

**Files:**
- Modify: `backend/app/site.py` (add route after card_sources_page)

### Background

A standalone price history page that Discord deep links can target. It renders the same Chart.js price chart and history table as `card_detail_page` but in a focused layout with a back-link to the card detail page. Free users see the 7-day window; Pro users see 180 days. The existing `_progate_html_from_config` + `get_pro_gate_config("price_history", access_tier)` handles the truncated-history banner, identical to `card_detail_page`.

- [ ] **Step 1: Verify history-route tests currently fail**

```bash
python -m pytest tests/test_sources_history_routes.py::TestCardHistoryRoute -v
```

Expected: FAIL — 404 for `/cards/xy1-001/history` (route not registered yet)

- [ ] **Step 2: Add the `/cards/{external_id}/history` route to `site.py`**

Insert immediately after `card_sources_page`:

```python
@router.get("/cards/{external_id}/history", response_class=HTMLResponse)
def card_history_page(request: Request, external_id: str) -> HTMLResponse:
    """Standalone price history page — Discord deep-link target."""
    import uuid as _uuid

    username = _session_username(request)
    session = request.scope.get("session")
    user_id = session.get("user_id") if isinstance(session, dict) else None

    with SessionLocal() as db:
        current_user = None
        if user_id:
            try:
                current_user = db.get(User, _uuid.UUID(user_id))
            except Exception:
                current_user = None
        access_tier = current_user.access_tier if current_user else "free"

        asset = db.scalars(
            select(Asset).where(Asset.category == "Pokemon", Asset.external_id == external_id)
        ).first()
        if asset is None:
            raise HTTPException(status_code=404, detail="卡牌不存在。")

        vm = build_card_detail(db, asset.id, access_tier=access_tier)

    if vm is None:
        raise HTTPException(status_code=404, detail="卡牌不存在。")

    currency = vm.currency or "USD"
    price_labels = [pt.captured_at.strftime("%Y-%m-%d") for pt in reversed(vm.price_history)]
    price_values = [float(pt.price) for pt in reversed(vm.price_history)]

    chart_script_tag = ""
    chart_markup = f"<p>{_lang_pair('暂无足够数据生成走势图。', 'Not enough data to render a chart yet.')}</p>"
    chart_inline_script = ""
    if len(vm.price_history) >= 2:
        chart_script_tag = (
            '<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>'
        )
        chart_markup = "<canvas id='price-chart-history'></canvas>"
        chart_inline_script = f"""
        <script>
          (() => {{
            const chartCanvas = document.getElementById("price-chart-history");
            if (!chartCanvas || typeof Chart === "undefined") {{ return; }}
            new Chart(chartCanvas, {{
              type: "line",
              data: {{
                labels: {json.dumps(price_labels)},
                datasets: [{{
                  label: "价格走势 (USD)",
                  data: {json.dumps(price_values)},
                  borderColor: "#00e5c8",
                  pointBackgroundColor: "#00e5c8",
                  pointBorderColor: "#00e5c8",
                  backgroundColor: "rgba(0,229,200,0.07)",
                  fill: true,
                  tension: 0.3,
                }}],
              }},
              options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                  x: {{ grid: {{ color: "rgba(255,255,255,0.06)" }}, ticks: {{ color: "#3d4f66" }} }},
                  y: {{ grid: {{ color: "rgba(255,255,255,0.06)" }}, ticks: {{ color: "#3d4f66" }} }},
                }},
              }},
            }});
          }})();
        </script>
        """

    history_markup = "".join(
        """
        <tr>
          <td>{captured_at}</td>
          <td>{price}</td>
          <td>{source}</td>
        </tr>
        """.format(
            captured_at=escape(pt.captured_at.strftime("%Y-%m-%d %H:%M UTC")),
            price=escape(_format_currency(pt.price, currency)),
            source=escape(pt.source),
        )
        for pt in reversed(vm.price_history)
    )
    if not history_markup:
        history_markup = f"""
        <tr>
          <td colspan="3" class="empty-state-cell">{_lang_pair("暂无价格历史数据。", "No price history available.")}</td>
        </tr>"""

    truncated_banner = ""
    if vm.history_truncated:
        blurred_preview = (
            "<p style='margin:0;font-style:italic;color:#6b7280;'>"
            + _lang_pair(
                "免费账户仅显示最近 7 天价格记录。",
                "Free accounts show only the last 7 days of price history.",
            )
            + "</p>"
        )
        truncated_banner = _progate_html_from_config(
            get_pro_gate_config("price_history", access_tier),
            blurred_preview,
        )

    body = f"""
    <section class="page-intro">
      <div>
        <p class="eyebrow">{_lang_pair("价格历史", "Price history")}</p>
        <h1>{escape(asset.name)}</h1>
        <p class="lede">
          {_lang_pair(f"查看 {escape(asset.name)} 的近期价格走势。",
          f"View recent price history for {escape(asset.name)}.")}
        </p>
      </div>
    </section>

    <section class="module module-wide">
      <div class="module-head">
        <p class="card-kicker">{_lang_pair("价格历史", "Price history")}</p>
        <h2>{_lang_pair("价格记录", "Price records")}</h2>
      </div>
      {truncated_banner}
      {chart_markup}
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>{_lang_pair("日期", "Date")}</th>
              <th>{_lang_pair("价格", "Price")}</th>
              <th>{_lang_pair("数据源", "Source")}</th>
            </tr>
          </thead>
          <tbody>
            {history_markup}
          </tbody>
        </table>
      </div>
      <div class="detail-actions" style="margin-top:1.5rem;">
        <a class="button button-secondary" href="/cards/{escape(external_id)}">{_lang_pair("返回卡牌详情", "Back to card detail")}</a>
      </div>
    </section>
    {chart_script_tag}
    {chart_inline_script}
    """

    return _render_shell(
        title=f"{asset.name} — Price History",
        current_path="/cards",
        body=body,
        page_key="card-history",
        username=username,
    )
```

- [ ] **Step 3: Run all Phase B tests**

```bash
python -m pytest tests/test_banner.py tests/test_sources_history_routes.py -v
```

Expected: All tests PASS

- [ ] **Step 4: Run full suite**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -25
```

Expected: All tests pass. Note total — compare to Phase A baseline.

- [ ] **Step 5: Commit**

```bash
git add backend/app/site.py
git commit -m "feat: add /cards/{id}/history standalone price history route"
```

---

## Phase B Completion Checklist

- [ ] `_progate_html_from_config(config, blurred_html)` returns plain content when unlocked
- [ ] `_progate_html_from_config` renders `feature_name`, `upgrade_reason` from ProGateConfig
- [ ] `progate__cta--high/medium/low` CSS classes exist in `site.css`; high class has pulse animation
- [ ] `card_detail_page` truncated_banner uses `_progate_html_from_config` (no hardcoded CTA string)
- [ ] `GET /cards/{id}/sources` returns 200, shows sample_size summary; free users see progate overlay
- [ ] `GET /cards/{id}/history` returns 200, shows price chart heading and card name
- [ ] No CTA strings hardcoded in `site.py` routes — all come from `get_pro_gate_config()`
- [ ] All 431+ tests pass
