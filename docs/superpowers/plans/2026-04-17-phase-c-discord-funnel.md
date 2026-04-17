# Phase C: Discord Traffic Funnel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a UTM-tagged web link layer for all Discord Bot slash commands, add `ResponseTemplates.price_alert()` with credibility data, and build three Discord-specific landing pages in `site.py` to convert Discord traffic into registered/Pro users.

**Architecture:** Three independent layers. Layer 1 — `bot/link_builder.py` module with `make_web_link()` wired into every embed handler via `embed.url`. Layer 2 — `ResponseTemplates` class inside `bot/main.py` for enriched price alert formatting. Layer 3 — three new FastAPI routes in `site.py` (`/welcome-from-discord`, `/upgrade-from-discord`, `/signals/explained`) plus an `extract_utm_params()` helper. Embed builder function signatures are unchanged; `embed.url` is set in the command handler after the builder is called, so no existing tests break.

**Tech Stack:** Python 3.12, FastAPI, discord.py, `urllib.parse.urlencode`, `unittest.TestCase` (no pytest fixtures), `starlette.testclient.TestClient` for route tests, `SessionLocal()` context manager for DB access.

---

## Pre-task: Create Phase C branch

```bash
git checkout main
git pull
git checkout -b feat/phase-c-discord-funnel
```

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `bot/link_builder.py` | **Create** | `BASE_URL` constant + `make_web_link()` — single source of truth for all bot URLs |
| `bot/main.py` | **Modify** | Import `make_web_link`; set `embed.url` in all 10 command handlers; add `ResponseTemplates` class |
| `backend/app/site.py` | **Modify** | Add `extract_utm_params()` helper + three Discord landing routes |
| `tests/test_link_builder.py` | **Create** | Unit tests for `make_web_link()` |
| `tests/test_bot_embed_urls.py` | **Create** | Tests that each command handler sets `embed.url` |
| `tests/test_response_templates.py` | **Create** | Unit tests for `ResponseTemplates.price_alert()` |
| `tests/test_discord_landing_routes.py` | **Create** | Route tests for the three new landing pages |

---

## Task 1: `bot/link_builder.py` — UTM link builder

**Files:**
- Create: `bot/link_builder.py`
- Create: `tests/test_link_builder.py`

### Background

Every bot embed needs a clickable title/URL back to the web app, with UTM params so we can track Discord → web conversion in server logs. `make_web_link(path, source_context)` takes a web path (`/cards`, `/dashboard`) and a dict with required key `command_type` + `campaign`, plus optional `signal_type`, `card_id`, `user_tier`. `BASE_URL` is read from settings at import time.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_link_builder.py
import unittest
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs


class TestMakeWebLink(unittest.TestCase):
    def setUp(self):
        # Patch BASE_URL after import so tests are isolated from real settings
        import bot.link_builder as lb
        self._patcher = patch.object(lb, "BASE_URL", "http://localhost:8000")
        self._patcher.start()
        import importlib
        importlib.reload(lb)
        self._lb = lb

    def tearDown(self):
        self._patcher.stop()

    def _parse(self, url: str) -> tuple[str, dict]:
        parsed = urlparse(url)
        return parsed.path, parse_qs(parsed.query)

    def test_required_utm_params_present(self):
        import bot.link_builder as lb
        lb.BASE_URL = "http://localhost:8000"
        from bot.link_builder import make_web_link
        url = make_web_link("/cards", {"command_type": "slash_command", "campaign": "card_discovery"})
        path, qs = self._parse(url)
        self.assertEqual(path, "/cards")
        self.assertEqual(qs["utm_source"], ["discord"])
        self.assertEqual(qs["utm_medium"], ["slash_command"])
        self.assertEqual(qs["utm_campaign"], ["card_discovery"])
        self.assertEqual(qs["from"], ["discord"])

    def test_optional_signal_type(self):
        from bot.link_builder import make_web_link
        url = make_web_link("/signals", {
            "command_type": "price_alert",
            "campaign": "card_discovery",
            "signal_type": "BREAKOUT",
        })
        _, qs = self._parse(url)
        self.assertEqual(qs["utm_content"], ["BREAKOUT"])

    def test_optional_card_id(self):
        from bot.link_builder import make_web_link
        url = make_web_link("/cards/abc123", {
            "command_type": "price_alert",
            "campaign": "card_discovery",
            "card_id": "abc123",
        })
        _, qs = self._parse(url)
        self.assertEqual(qs["ref"], ["abc123"])

    def test_optional_user_tier(self):
        from bot.link_builder import make_web_link
        url = make_web_link("/dashboard", {
            "command_type": "slash_command",
            "campaign": "engagement",
            "user_tier": "pro",
        })
        _, qs = self._parse(url)
        self.assertEqual(qs["tier"], ["pro"])

    def test_no_signal_type_no_utm_content(self):
        from bot.link_builder import make_web_link
        url = make_web_link("/cards", {"command_type": "slash_command", "campaign": "card_discovery"})
        _, qs = self._parse(url)
        self.assertNotIn("utm_content", qs)

    def test_base_url_used(self):
        from bot.link_builder import make_web_link
        import bot.link_builder as lb
        lb.BASE_URL = "https://flashcardplanet.com"
        url = make_web_link("/cards", {"command_type": "slash_command", "campaign": "card_discovery"})
        self.assertTrue(url.startswith("https://flashcardplanet.com/cards?"))

    def test_path_preserved(self):
        from bot.link_builder import make_web_link
        url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "engagement"})
        path, _ = self._parse(url)
        self.assertEqual(path, "/dashboard")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_link_builder.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` for `bot.link_builder`.

- [ ] **Step 3: Create `bot/link_builder.py`**

```python
from __future__ import annotations

from urllib.parse import urlencode

from backend.app.core.config import get_settings

BASE_URL: str = get_settings().backend_base_url.rstrip("/")


def make_web_link(path: str, source_context: dict) -> str:
    params: dict[str, str] = {
        "utm_source": "discord",
        "utm_medium": source_context["command_type"],
        "utm_campaign": source_context["campaign"],
        "from": "discord",
    }
    if source_context.get("signal_type"):
        params["utm_content"] = source_context["signal_type"]
    if source_context.get("card_id"):
        params["ref"] = str(source_context["card_id"])
    if source_context.get("user_tier"):
        params["tier"] = source_context["user_tier"]
    return f"{BASE_URL}{path}?{urlencode(params)}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_link_builder.py -v
```

Expected: 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add bot/link_builder.py tests/test_link_builder.py
git commit -m "feat: add link_builder module with make_web_link() for UTM-tagged bot embeds"
```

---

## Task 2: Wire `embed.url` into all 10 slash command handlers

**Files:**
- Modify: `bot/main.py` (lines ~1–10 imports, ~632–848 command handlers)
- Create: `tests/test_bot_embed_urls.py`

### Background

There are 10 slash commands. None of them currently set `embed.url`. The approach: import `make_web_link` at the top of `bot/main.py`, then in each command handler capture the embed into a variable, set `embed.url = make_web_link(...)`, and pass the embed to `followup.send()`.

Embed builder function signatures are NOT changed. Existing tests continue to test builder outputs only.

URL mapping:
- `price`, `predict`, `history` → `/cards` (card search, since API responses don't return `external_id`)
- `topmovers`, `topvalue` → `/dashboard`
- `watch`, `unwatch`, `watchlist` → `/dashboard`
- `alerts`, `alerthistory` → `/dashboard`
- `watch` TierError path → `/upgrade-from-discord` (pro conversion)

Campaign mapping:
- card lookup commands (`price`, `predict`, `history`, `topmovers`, `topvalue`) → `card_discovery`
- user management commands (`watch`, `unwatch`, `watchlist`, `alerts`, `alerthistory`) → `engagement`
- TierError on `watch` → `pro_conversion`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bot_embed_urls.py
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse, parse_qs


def _parse_url(url: str) -> tuple[str, dict]:
    parsed = urlparse(url)
    return parsed.path, parse_qs(parsed.query)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestEmbedUrlsPrice(unittest.TestCase):
    def _make_interaction(self):
        interaction = MagicMock()
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()
        return interaction

    def test_price_embed_url_set(self):
        interaction = self._make_interaction()
        fake_results = [{"name": "Pikachu", "latest_price": "10.00", "currency": "USD",
                         "liquidity_score": None, "liquidity_label": None,
                         "sales_count_7d": None, "sales_count_30d": None,
                         "days_since_last_sale": None, "source_count": None,
                         "alert_confidence": None, "alert_confidence_label": None,
                         "percent_change": None, "source": "ebay", "captured_at": None,
                         "image_url": None, "category": None, "set_name": None}]
        with patch("bot.main.client") as mock_client, \
             patch("bot.main.make_web_link", return_value="http://localhost:8000/cards?utm_source=discord") as mock_link:
            mock_client.fetch_price = AsyncMock(return_value=fake_results)
            from bot.main import price
            run(price.callback(interaction, name="Pikachu"))
        mock_link.assert_called_once()
        args = mock_link.call_args
        self.assertEqual(args[0][0], "/cards")
        self.assertEqual(args[0][1]["command_type"], "slash_command")
        self.assertEqual(args[0][1]["campaign"], "card_discovery")
        sent_embed = interaction.followup.send.call_args[1]["embed"]
        self.assertEqual(sent_embed.url, "http://localhost:8000/cards?utm_source=discord")

    def test_predict_embed_url_set(self):
        interaction = self._make_interaction()
        fake_results = [{"name": "Pikachu", "current_price": "10.00", "currency": "USD",
                         "prediction": "Up", "up_probability": "70", "down_probability": "10",
                         "flat_probability": "20", "points_used": 5, "captured_at": None,
                         "reason": "test", "image_url": None, "set_name": None}]
        with patch("bot.main.client") as mock_client, \
             patch("bot.main.make_web_link", return_value="http://localhost:8000/cards?utm_source=discord") as mock_link:
            mock_client.fetch_prediction = AsyncMock(return_value=fake_results)
            from bot.main import predict
            run(predict.callback(interaction, name="Pikachu"))
        mock_link.assert_called_once()
        self.assertEqual(mock_link.call_args[0][0], "/cards")
        self.assertEqual(mock_link.call_args[0][1]["campaign"], "card_discovery")

    def test_history_embed_url_set(self):
        interaction = self._make_interaction()
        fake_result = {"name": "Pikachu", "history": [], "points_returned": 0,
                       "current_price": None, "currency": None, "image_url": None,
                       "set_name": None, "liquidity_score": None, "liquidity_label": None,
                       "sales_count_7d": None, "sales_count_30d": None,
                       "days_since_last_sale": None, "source_count": None,
                       "alert_confidence": None, "alert_confidence_label": None}
        with patch("bot.main.client") as mock_client, \
             patch("bot.main.make_web_link", return_value="http://localhost:8000/cards?utm_source=discord") as mock_link:
            mock_client.fetch_history = AsyncMock(return_value=fake_result)
            from bot.main import history
            run(history.callback(interaction, name="Pikachu", limit=5))
        mock_link.assert_called_once()
        self.assertEqual(mock_link.call_args[0][0], "/cards")

    def test_topmovers_embed_url_set(self):
        interaction = self._make_interaction()
        fake_movers = [{"name": "Pikachu", "percent_change": "5.0", "latest_price": "10.00",
                        "liquidity_score": None, "liquidity_label": None,
                        "alert_confidence": None, "alert_confidence_label": None,
                        "sales_count_7d": None, "sales_count_30d": None,
                        "days_since_last_sale": None, "source_count": None}]
        with patch("bot.main.client") as mock_client, \
             patch("bot.main.make_web_link", return_value="http://localhost:8000/dashboard?utm_source=discord") as mock_link:
            mock_client.fetch_top_movers = AsyncMock(return_value=fake_movers)
            from bot.main import topmovers
            run(topmovers.callback(interaction, limit=5))
        mock_link.assert_called_once()
        self.assertEqual(mock_link.call_args[0][0], "/dashboard")
        self.assertEqual(mock_link.call_args[0][1]["campaign"], "card_discovery")

    def test_topvalue_embed_url_set(self):
        interaction = self._make_interaction()
        fake_items = [{"name": "Pikachu", "latest_price": "10.00", "currency": "USD",
                       "set_name": None, "category": None, "captured_at": None}]
        with patch("bot.main.client") as mock_client, \
             patch("bot.main.make_web_link", return_value="http://localhost:8000/dashboard?utm_source=discord") as mock_link:
            mock_client.fetch_top_value = AsyncMock(return_value=fake_items)
            from bot.main import topvalue
            run(topvalue.callback(interaction, limit=10))
        mock_link.assert_called_once()
        self.assertEqual(mock_link.call_args[0][0], "/dashboard")

    def test_watchlist_embed_url_set(self):
        interaction = self._make_interaction()
        interaction.user = MagicMock()
        interaction.user.id = 12345
        fake_items = [{"name": "Pikachu", "threshold_up_percent": None,
                       "threshold_down_percent": None, "target_price": None}]
        with patch("bot.main.client") as mock_client, \
             patch("bot.main.make_web_link", return_value="http://localhost:8000/dashboard?utm_source=discord") as mock_link:
            mock_client.fetch_watchlist = AsyncMock(return_value=fake_items)
            from bot.main import watchlist
            run(watchlist.callback(interaction))
        mock_link.assert_called_once()
        self.assertEqual(mock_link.call_args[0][0], "/dashboard")
        self.assertEqual(mock_link.call_args[0][1]["campaign"], "engagement")

    def test_alerts_embed_url_set(self):
        interaction = self._make_interaction()
        interaction.user = MagicMock()
        interaction.user.id = 12345
        with patch("bot.main.client") as mock_client, \
             patch("bot.main.make_web_link", return_value="http://localhost:8000/dashboard?utm_source=discord") as mock_link:
            mock_client.fetch_alerts = AsyncMock(return_value=[])
            from bot.main import alerts
            run(alerts.callback(interaction))
        mock_link.assert_called_once()
        self.assertEqual(mock_link.call_args[0][0], "/dashboard")
        self.assertEqual(mock_link.call_args[0][1]["campaign"], "engagement")

    def test_watch_tier_error_embed_url_points_to_upgrade(self):
        from bot.api_client import TierError
        interaction = self._make_interaction()
        interaction.user = MagicMock()
        interaction.user.id = 12345
        with patch("bot.main.client") as mock_client, \
             patch("bot.main.make_web_link", return_value="http://localhost:8000/upgrade-from-discord?utm_source=discord") as mock_link:
            mock_client.create_watch = AsyncMock(side_effect=TierError("limit", "/upgrade"))
            from bot.main import watch
            run(watch.callback(interaction, asset_name="Pikachu",
                               threshold_up_percent=None, threshold_down_percent=None,
                               target_price=None, predict_signal_change=None,
                               predict_up_probability_above=None, predict_down_probability_above=None))
        mock_link.assert_called_once()
        self.assertEqual(mock_link.call_args[0][0], "/upgrade-from-discord")
        self.assertEqual(mock_link.call_args[0][1]["campaign"], "pro_conversion")

    def test_alerthistory_embed_url_set(self):
        interaction = self._make_interaction()
        interaction.user = MagicMock()
        interaction.user.id = 12345
        with patch("bot.main.client") as mock_client, \
             patch("bot.main.make_web_link", return_value="http://localhost:8000/dashboard?utm_source=discord") as mock_link:
            mock_client.fetch_alert_history = AsyncMock(return_value=[])
            from bot.main import alerthistory
            run(alerthistory.callback(interaction, limit=10, asset_name=None))
        mock_link.assert_called_once()
        self.assertEqual(mock_link.call_args[0][0], "/dashboard")
        self.assertEqual(mock_link.call_args[0][1]["campaign"], "engagement")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_bot_embed_urls.py -v
```

Expected: 9 failures — `make_web_link` not imported in `bot.main`, and `embed.url` not being set.

- [ ] **Step 3: Add import and wire `embed.url` in `bot/main.py`**

Add to the imports at the top of `bot/main.py` (after the existing `from bot.api_client import BackendClient, TierError` line):

```python
from bot.link_builder import make_web_link
```

Then update each command handler as shown. Only the code inside the handler changes — no builder function signatures change.

**`price` command** — change the send line from:
```python
    await interaction.followup.send(embed=build_price_embed(results[0], len(results)))
```
to:
```python
    embed = build_price_embed(results[0], len(results))
    embed.url = make_web_link("/cards", {"command_type": "slash_command", "campaign": "card_discovery"})
    await interaction.followup.send(embed=embed)
```

**`predict` command** — change:
```python
    await interaction.followup.send(embed=build_prediction_embed(results[0], len(results)))
```
to:
```python
    embed = build_prediction_embed(results[0], len(results))
    embed.url = make_web_link("/cards", {"command_type": "slash_command", "campaign": "card_discovery"})
    await interaction.followup.send(embed=embed)
```

**`history` command** — change:
```python
    await interaction.followup.send(embed=build_history_embed(result, limit))
```
to:
```python
    embed = build_history_embed(result, limit)
    embed.url = make_web_link("/cards", {"command_type": "slash_command", "campaign": "card_discovery"})
    await interaction.followup.send(embed=embed)
```

**`watch` command** — the TierError branch creates an inline `discord.Embed(...)`. Capture it and set `.url`:
```python
    except TierError as exc:
        embed = discord.Embed(
            title="Watchlist limit reached",
            description=(
                f"{exc}\n\n"
                f"[Upgrade to Pro]({exc.upgrade_url}) for unlimited watchlists."
            ),
            color=EMBED_COLOR_WARNING,
        )
        embed.url = make_web_link("/upgrade-from-discord", {"command_type": "slash_command", "campaign": "pro_conversion"})
        await interaction.followup.send(embed=embed)
        return
```

The success path of `watch` sends `content=result["message"], embed=build_watch_embed(...)`. Change to:
```python
    embed = build_watch_embed(
        result=result,
        asset_name=asset_name,
        threshold_up_percent=threshold_up_percent,
        threshold_down_percent=threshold_down_percent,
        target_price=target_price,
        predict_signal_change=predict_signal_change,
        predict_up_probability_above=predict_up_probability_above,
        predict_down_probability_above=predict_down_probability_above,
    )
    embed.url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "engagement"})
    await interaction.followup.send(content=result["message"], embed=embed)
```

**`unwatch` command** — change:
```python
    await interaction.followup.send(content=result["message"], embed=build_unwatch_embed(asset_name))
```
to:
```python
    embed = build_unwatch_embed(asset_name)
    embed.url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "engagement"})
    await interaction.followup.send(content=result["message"], embed=embed)
```

**`watchlist` command** — both the empty and non-empty branches:
```python
    if not items:
        embed = build_empty_watchlist_embed()
        embed.url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "engagement"})
        await interaction.followup.send(embed=embed)
        return
    embed = build_watchlist_embed(items)
    embed.url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "engagement"})
    await interaction.followup.send(embed=embed)
```

**`alerts` command** — both branches:
```python
    if not items:
        embed = build_empty_alerts_embed()
        embed.url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "engagement"})
        await interaction.followup.send(embed=embed)
        return
    embed = build_alerts_embed(items)
    embed.url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "engagement"})
    await interaction.followup.send(embed=embed)
```

**`topmovers` command** — the "no meaningful movers" branch sends a string, not an embed, so no change needed there. The success branch:
```python
    embed = build_topmovers_embed(movers, limit)
    embed.url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "card_discovery"})
    await interaction.followup.send(embed=embed)
```

**`topvalue` command** — success branch:
```python
    embed = build_topvalue_embed(items, limit)
    embed.url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "card_discovery"})
    await interaction.followup.send(embed=embed)
```

**`alerthistory` command** — both branches:
```python
    if not items:
        embed = build_empty_alert_history_embed()
        embed.url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "engagement"})
        await interaction.followup.send(embed=embed)
        return
    embed = build_alert_history_embed(items, limit)
    embed.url = make_web_link("/dashboard", {"command_type": "slash_command", "campaign": "engagement"})
    await interaction.followup.send(embed=embed)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_bot_embed_urls.py -v
```

Expected: 9 PASSED.

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add bot/main.py tests/test_bot_embed_urls.py
git commit -m "feat: wire embed.url into all 10 slash command handlers via make_web_link"
```

---

## Task 3: `ResponseTemplates.price_alert()` in `bot/main.py`

**Files:**
- Modify: `bot/main.py` (add `ResponseTemplates` class, after the embed builder functions, before `get_test_guild`)
- Create: `tests/test_response_templates.py`

### Background

`ResponseTemplates.price_alert(card_data)` formats a rich price alert dict for use when the bot fires a watchlist alert. It uses three optional fields from `card_data`: `sample_size`, `match_confidence`, and `pro_gate_config` (a `ProGateConfig` instance). It uses `make_web_link` to embed the web URL. `card_data` is a duck-typed object (or mock) — no import of a specific dataclass is needed here.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_response_templates.py
import unittest
from unittest.mock import MagicMock, patch


def _make_card_data(
    *,
    name: str = "Pikachu",
    id: str = "pika-001",
    change: float = 5.2,
    sample_size: int | None = None,
    match_confidence: float | None = None,
    pro_gate_config=None,
):
    card = MagicMock()
    card.name = name
    card.id = id
    card.change = change
    card.sample_size = sample_size
    card.match_confidence = match_confidence
    card.pro_gate_config = pro_gate_config
    return card


class TestResponseTemplatesPriceAlert(unittest.TestCase):
    def setUp(self):
        import bot.link_builder as lb
        self._patcher = patch.object(lb, "BASE_URL", "http://localhost:8000")
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_basic_structure_returned(self):
        from bot.main import ResponseTemplates
        result = ResponseTemplates.price_alert(_make_card_data())
        self.assertIn("embed", result)
        self.assertIn("title", result["embed"])
        self.assertIn("description", result["embed"])
        self.assertIn("url", result["embed"])

    def test_title_contains_card_name(self):
        from bot.main import ResponseTemplates
        result = ResponseTemplates.price_alert(_make_card_data(name="Charizard"))
        self.assertIn("Charizard", result["embed"]["title"])

    def test_description_contains_price_change(self):
        from bot.main import ResponseTemplates
        result = ResponseTemplates.price_alert(_make_card_data(change=7.5))
        self.assertIn("7.5", result["embed"]["description"])

    def test_sample_size_included_when_present(self):
        from bot.main import ResponseTemplates
        result = ResponseTemplates.price_alert(_make_card_data(sample_size=42))
        self.assertIn("42", result["embed"]["description"])
        self.assertIn("sales", result["embed"]["description"])

    def test_sample_size_omitted_when_none(self):
        from bot.main import ResponseTemplates
        result = ResponseTemplates.price_alert(_make_card_data(sample_size=None))
        self.assertNotIn("sales", result["embed"]["description"])

    def test_high_confidence_shows_checkmark(self):
        from bot.main import ResponseTemplates
        result = ResponseTemplates.price_alert(_make_card_data(match_confidence=95))
        self.assertIn("✅", result["embed"]["description"])
        self.assertIn("95", result["embed"]["description"])

    def test_low_confidence_shows_warning(self):
        from bot.main import ResponseTemplates
        result = ResponseTemplates.price_alert(_make_card_data(match_confidence=75))
        self.assertIn("⚠️", result["embed"]["description"])

    def test_pro_gate_locked_appends_upgrade_message(self):
        from bot.main import ResponseTemplates
        gate = MagicMock()
        gate.is_locked = True
        gate.to_bot_config.return_value = {
            "locked_message": "🔥 See long-term patterns (Pro Only)",
            "cta_text": "Upgrade to Pro",
            "upgrade_link": "/upgrade-from-discord",
        }
        result = ResponseTemplates.price_alert(_make_card_data(pro_gate_config=gate))
        self.assertIn("Pro Only", result["embed"]["description"])

    def test_pro_gate_unlocked_no_upgrade_message(self):
        from bot.main import ResponseTemplates
        gate = MagicMock()
        gate.is_locked = False
        result = ResponseTemplates.price_alert(_make_card_data(pro_gate_config=gate))
        self.assertNotIn("Pro Only", result["embed"]["description"])

    def test_url_uses_make_web_link_with_card_id(self):
        from bot.main import ResponseTemplates
        with patch("bot.main.make_web_link", return_value="http://test/cards/pika-001?utm_source=discord") as mock_link:
            result = ResponseTemplates.price_alert(_make_card_data(id="pika-001"))
        mock_link.assert_called_once()
        args = mock_link.call_args
        self.assertIn("pika-001", args[0][0])
        self.assertEqual(args[0][1]["command_type"], "price_alert")
        self.assertEqual(args[0][1]["card_id"], "pika-001")
        self.assertEqual(result["embed"]["url"], "http://test/cards/pika-001?utm_source=discord")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_response_templates.py -v
```

Expected: `ImportError` — `ResponseTemplates` not defined in `bot.main`.

- [ ] **Step 3: Add `ResponseTemplates` class to `bot/main.py`**

Insert this class after the `build_empty_alert_history_embed` function (around line 584, before `get_test_guild`):

```python
class ResponseTemplates:
    @staticmethod
    def price_alert(card_data) -> dict:
        base_desc = f"Price moved {card_data.change}%"
        enhancements = []

        if getattr(card_data, "sample_size", None):
            enhancements.append(f"📊 Based on {card_data.sample_size} sales")

        if getattr(card_data, "match_confidence", None) is not None:
            icon = "✅" if card_data.match_confidence >= 90 else "⚠️"
            enhancements.append(f"{icon} {card_data.match_confidence}% confident")

        if getattr(card_data, "pro_gate_config", None) and card_data.pro_gate_config.is_locked:
            bot_cfg = card_data.pro_gate_config.to_bot_config()
            enhancements.append(f"\n{bot_cfg['locked_message']}")

        description = base_desc + ("\n" + "\n".join(enhancements) if enhancements else "")
        return {
            "embed": {
                "title": f"🔥 {card_data.name} Price Alert",
                "description": description,
                "url": make_web_link(f"/cards/{card_data.id}", {
                    "command_type": "price_alert",
                    "campaign": "card_discovery",
                    "card_id": card_data.id,
                }),
            }
        }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_response_templates.py -v
```

Expected: 10 PASSED.

- [ ] **Step 5: Commit**

```bash
git add bot/main.py tests/test_response_templates.py
git commit -m "feat: add ResponseTemplates.price_alert() with credibility data and UTM web link"
```

---

## Task 4: Discord landing pages in `site.py`

**Files:**
- Modify: `backend/app/site.py` (add `extract_utm_params` helper + 3 routes near end of file)
- Create: `tests/test_discord_landing_routes.py`

### Background

Three new routes serve Discord-arriving visitors. All use `_render_shell()` for consistent nav/footer. Auth pattern: read `request.scope.get("session")` for `user_id`, redirect to `/auth/login` if login required. Access tier: look up `User` via `db.get(User, uuid.UUID(user_id))`.

- `/welcome-from-discord` — public; if already logged in redirects to `/cards/{ref}` or `/dashboard`; otherwise shows a friendly welcome page with CTA to log in
- `/upgrade-from-discord` — requires login; if already Pro redirects to `/signals`; otherwise shows upgrade pitch
- `/signals/explained` — fully public; explains the signals feed for curious Discord users

`extract_utm_params(request)` returns a dict of whichever UTM keys are present in `request.query_params`.

**Import additions needed at top of `site.py`** — `User` model is already imported; `uuid` is already imported. `RedirectResponse` is already imported.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_discord_landing_routes.py
import unittest
import uuid

from starlette.testclient import TestClient

from backend.app.db.session import SessionLocal
from backend.app.main import app
from backend.app.models.user import User


def _create_user(db, *, access_tier: str = "free") -> User:
    user = User(
        id=uuid.uuid4(),
        discord_user_id=str(uuid.uuid4()),
        username=f"testuser_{uuid.uuid4().hex[:6]}",
        access_tier=access_tier,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


class TestExtractUtmParams(unittest.TestCase):
    def test_returns_present_params(self):
        from backend.app.site import extract_utm_params
        from starlette.requests import Request
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/welcome-from-discord",
            "query_string": b"utm_source=discord&utm_medium=slash_command&utm_campaign=card_discovery",
            "headers": [],
        }
        request = Request(scope)
        result = extract_utm_params(request)
        self.assertEqual(result["utm_source"], "discord")
        self.assertEqual(result["utm_medium"], "slash_command")
        self.assertEqual(result["utm_campaign"], "card_discovery")

    def test_omits_absent_params(self):
        from backend.app.site import extract_utm_params
        from starlette.requests import Request
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/welcome-from-discord",
            "query_string": b"utm_source=discord",
            "headers": [],
        }
        request = Request(scope)
        result = extract_utm_params(request)
        self.assertNotIn("utm_content", result)
        self.assertNotIn("ref", result)


class TestDiscordWelcomeRoute(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=True)

    def test_unauthenticated_shows_welcome_page(self):
        response = self.client.get("/welcome-from-discord", follow_redirects=False)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"discord", response.content.lower())

    def test_authenticated_redirects_to_dashboard(self):
        with SessionLocal() as db:
            user = _create_user(db)
        with self.client as c:
            with c.session_transaction() as sess:
                sess["username"] = user.username
                sess["user_id"] = str(user.id)
            response = c.get("/welcome-from-discord", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/dashboard", response.headers["location"])

    def test_authenticated_with_ref_redirects_to_card(self):
        with SessionLocal() as db:
            user = _create_user(db)
        with self.client as c:
            with c.session_transaction() as sess:
                sess["username"] = user.username
                sess["user_id"] = str(user.id)
            response = c.get("/welcome-from-discord?ref=charizard-001", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("charizard-001", response.headers["location"])


class TestDiscordUpgradeRoute(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=True)

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get("/upgrade-from-discord", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login", response.headers["location"])

    def test_free_user_sees_upgrade_page(self):
        with SessionLocal() as db:
            user = _create_user(db, access_tier="free")
        with self.client as c:
            with c.session_transaction() as sess:
                sess["username"] = user.username
                sess["user_id"] = str(user.id)
            response = c.get("/upgrade-from-discord", follow_redirects=False)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"pro", response.content.lower())

    def test_pro_user_redirects_to_signals(self):
        with SessionLocal() as db:
            user = _create_user(db, access_tier="pro")
        with self.client as c:
            with c.session_transaction() as sess:
                sess["username"] = user.username
                sess["user_id"] = str(user.id)
            response = c.get("/upgrade-from-discord", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/signals", response.headers["location"])


class TestSignalsExplainedRoute(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=True)

    def test_public_page_returns_200(self):
        response = self.client.get("/signals/explained")
        self.assertEqual(response.status_code, 200)

    def test_page_contains_signals_content(self):
        response = self.client.get("/signals/explained")
        self.assertIn(b"signal", response.content.lower())
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_discord_landing_routes.py -v
```

Expected: `ImportError` for `extract_utm_params`, and 404s for the three routes.

- [ ] **Step 3: Add `extract_utm_params` and the three routes to `backend/app/site.py`**

Find the end of the file (after the last route, around line 2450+). Add:

```python
# ── Discord landing pages ─────────────────────────────────────────────────────

def extract_utm_params(request: Request) -> dict:
    keys = ("utm_source", "utm_medium", "utm_campaign", "utm_content", "ref", "tier", "from")
    return {k: request.query_params[k] for k in keys if k in request.query_params}


@router.get("/welcome-from-discord", response_class=HTMLResponse)
def discord_welcome(request: Request) -> HTMLResponse:
    username = _session_username(request)
    if username:
        ref = request.query_params.get("ref")
        dest = f"/cards/{ref}?from=discord" if ref else "/dashboard?from=discord"
        return RedirectResponse(dest, status_code=302)
    body = """
    <section class="page-intro">
      <div>
        <p class="eyebrow">Welcome from Discord</p>
        <h1>You found the data behind the signals.</h1>
        <p class="lede">
          Flashcard Planet tracks collectible prices, generates buy/sell signals, and fires alerts
          when your watchlist moves. Everything you see in the Discord bot lives here, with charts,
          history, and source breakdowns.
        </p>
        <div class="hero-actions">
          <a class="button button-primary" href="/auth/login">Log in with Discord</a>
          <a class="button button-secondary" href="/signals">Browse signals</a>
        </div>
      </div>
    </section>
    """
    return _render_shell(
        title="Welcome from Discord",
        current_path="/welcome-from-discord",
        body=body,
        page_key="discord-welcome",
    )


@router.get("/upgrade-from-discord", response_class=HTMLResponse)
def discord_upgrade(request: Request) -> HTMLResponse:
    import uuid as _uuid
    session = request.scope.get("session")
    user_id = session.get("user_id") if isinstance(session, dict) else None
    if not user_id:
        return RedirectResponse("/auth/login?next=/upgrade-from-discord", status_code=302)

    with SessionLocal() as db:
        try:
            current_user = db.get(User, _uuid.UUID(user_id))
        except Exception:
            current_user = None

    access_tier = current_user.access_tier if current_user else "free"
    if access_tier == "pro":
        return RedirectResponse("/signals?from=discord", status_code=302)

    username = _session_username(request)
    body = f"""
    <section class="page-intro">
      <div>
        <p class="eyebrow">Upgrade to Pro</p>
        <h1>Unlock the full signal feed.</h1>
        <p class="lede">
          Free tier shows the top 5 signals. Pro unlocks the full feed, AI explanations,
          180-day price history, source breakdown, and unlimited alerts.
        </p>
        <div class="hero-actions">
          <a class="button button-primary" href="/pro">View Pro plans</a>
        </div>
      </div>
    </section>
    """
    return _render_shell(
        title="Upgrade to Pro",
        current_path="/upgrade-from-discord",
        body=body,
        page_key="discord-upgrade",
        username=username,
    )


@router.get("/signals/explained", response_class=HTMLResponse)
def signals_explained(request: Request) -> HTMLResponse:
    username = _session_username(request)
    body = """
    <section class="page-intro">
      <div>
        <p class="eyebrow">How signals work</p>
        <h1>Market signals, explained.</h1>
        <p class="lede">
          A signal fires when recent price data passes a statistical threshold indicating
          unusual movement — a BREAKOUT (sharp upward move), a MOVE (trend continuation),
          or a WATCH (elevated activity without a directional conviction).
        </p>
        <p>
          Signals are ranked by confidence score. Free users see the top 5. Pro users see the
          full feed with AI-generated explanations and historical signal accuracy.
        </p>
        <div class="hero-actions">
          <a class="button button-primary" href="/signals">View signals</a>
          <a class="button button-secondary" href="/upgrade-from-discord">Upgrade to Pro</a>
        </div>
      </div>
    </section>
    """
    return _render_shell(
        title="Signals Explained",
        current_path="/signals/explained",
        body=body,
        page_key="signals-explained",
        username=username,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_discord_landing_routes.py -v
```

Expected: 10 PASSED.

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all previously passing tests still pass, total test count increases by 10.

- [ ] **Step 6: Commit**

```bash
git add backend/app/site.py tests/test_discord_landing_routes.py
git commit -m "feat: add extract_utm_params and three Discord landing routes to site.py"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered in |
|---|---|
| All 9 (10) bot commands include UTM-tagged web link | Task 2 |
| `make_web_link()` used everywhere in bot — no hardcoded URLs | Task 1 + 2 |
| `ResponseTemplates.price_alert()` shows credibility data | Task 3 |
| `/welcome-from-discord` live | Task 4 |
| `/upgrade-from-discord` live | Task 4 |
| `/signals/explained` live | Task 4 |
| `extract_utm_params()` available in `site.py` | Task 4 |

**Note on spec discrepancy:** The spec says "9 bot commands" but `bot/main.py` has 10 (`price`, `predict`, `history`, `watch`, `unwatch`, `watchlist`, `alerts`, `topmovers`, `topvalue`, `alerthistory`). All 10 are covered.

**Placeholder scan:** No TBDs. All steps include complete code.

**Type consistency:**
- `make_web_link(path: str, source_context: dict) -> str` used consistently across Tasks 1, 2, 3, 4
- `extract_utm_params(request: Request) -> dict` defined in Task 4, used in tests
- `ResponseTemplates.price_alert(card_data) -> dict` defined and tested in Task 3
- `embed.url` is a `str | None` attribute on `discord.Embed` — valid to set
