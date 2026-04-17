# Flashcard Planet v3.1 Architecture Migration Design

**Date:** 2026-04-17  
**Approach:** Incremental layering (方案 2) — preserve `site.py`, add new service/boundary layers on top

---

## Overview

Three phases executed in strict order, each a prerequisite for the next:

1. **Phase A** — API boundary + unified permissions (foundation)
2. **Phase B** — Web Phase 2A feature enhancement (product capability)
3. **Phase C** — Discord traffic funnel (conversion)

---

## Phase A: Foundation — Unified Service Layer

### New Files

**`backend/app/core/data_service.py`**

Central data access class. Both Discord Bot and Web new routes call this; old `site.py` routes are untouched.

```python
class DataService:
    @staticmethod
    def get_signals(user_id: str, limit: int | None = None) -> SignalsResponse:
        access = check_user_access(user_id, "signals")
        signals_data = signals_service.get_latest(limit=access.signals_limit)
        return SignalsResponse(
            signals=signals_data,
            user_access=access,
            pro_gate_config=get_pro_gate_config("signals", access) if not access.is_pro else None,
        )

    @staticmethod
    def get_card_detail(card_id: str, user_id: str) -> CardDetailResponse:
        access = check_user_access(user_id, "card_detail")
        # NOTE: verify exact service module names against services/ at implementation time
        card_data = cards_service.get_card_detail(card_id)
        price_history = prices_service.get_history(card_id, days=access.price_history_days)
        return CardDetailResponse(
            card_data=card_data,
            price_history=price_history,
            sample_size=card_data.sample_size,
            match_confidence=card_data.match_confidence,
            user_access=access,
            pro_gate_config=get_pro_gate_config("price_history", access) if not access.is_pro else None,
        )

    @staticmethod
    def get_user_limits(user_id: str) -> AccessLevel:
        return check_user_access(user_id, "general")
```

**`backend/app/core/response_types.py`**

Shared dataclasses used by both Bot and Web — ensures identical data shape across consumers.

```python
@dataclass
class ProGateConfig:
    is_locked: bool
    feature_name: str = ""
    upgrade_reason: str = ""
    urgency: str = "medium"  # low | medium | high

    def to_web_config(self) -> dict:
        return {
            "maskType": "blur",
            "ctaText": f"Unlock {self.feature_name} — Pro Only",
            "urgency": self.urgency,
        }

    def to_bot_config(self) -> dict:
        return {
            "locked_message": f"🔒 {self.upgrade_reason} (Pro Only)",
            "cta_text": "Upgrade to Pro for full access",
            "upgrade_link": "/upgrade-from-discord",
        }

@dataclass
class CardDetailResponse:
    card_data: dict
    price_history: list
    sample_size: int
    match_confidence: float
    data_age: str           # e.g. "Updated 3 hours ago"
    user_access: "AccessLevel"
    pro_gate_config: ProGateConfig | None

@dataclass
class SignalsResponse:
    signals: list
    user_access: "AccessLevel"
    pro_gate_config: ProGateConfig | None
```

**`backend/app/core/permissions.py` — additions**

Add to the existing file:

```python
def check_user_access(user_id: str, feature: str) -> AccessLevel:
    """Unified access check — Bot and Web both call this."""
    ...

def get_pro_gate_config(feature: str, user_access: AccessLevel) -> ProGateConfig:
    strategies = {
        "price_history": ProGateConfig(
            is_locked=True,
            feature_name="Extended Price History",
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
    if user_access.is_pro:
        return ProGateConfig(is_locked=False)
    return strategies.get(feature, ProGateConfig(is_locked=True, upgrade_reason="Upgrade to Pro"))
```

### Pre-Phase A Verification Checklist

Before writing any new code, confirm these in the existing `services/` layer:

| Method | Required signature | Check |
|---|---|---|
| card detail service | `get_card_detail(card_id) → obj with .sample_size, .match_confidence` | |
| prices service | `get_history(card_id, days=N) → list` — `days` param must exist | |
| signals service | `get_latest(limit=N) → list` — `limit` param must exist | |

If a method doesn't support the required param, add it to the existing service file before building DataService. DataService wraps; it does not rewrite.

### DataService Growth Note

Current scope: ~4 methods. If it grows past 8 methods or domain boundaries become obvious (cards / signals / users are clearly separate), split into domain services with DataService as a facade:
```python
class DataService:
    cards = CardsDataService()
    signals = SignalsDataService()
    users = UserDataService()
```
Do not pre-split now — wait for the actual pain point.

**`backend/app/core/boundary_check.py`**

CI lint script. Fails if new Bot/Web code imports internal services directly, bypassing DataService.

```python
boundary_rules = {
    "forbidden_direct_imports": ["models.User", "services.signals", "services.prices"],
    "must_go_through": ["core.data_service.DataService"],
    "whitelist": ["core.permissions", "core.response_types", "core.config"],
}
```

### Completion Criteria

- [ ] `DataService.get_signals()` and `get_card_detail()` callable from both Bot and Web
- [ ] `ProGateConfig.to_web_config()` and `to_bot_config()` return correct shapes
- [ ] `boundary_check.py` runs in CI without errors on new code
- [ ] Old `site.py` routes untouched and still functional

---

## Phase B: Web Feature Enhancement

### B1: Credibility Indicators + Chart (depends on Phase A)

**Modified route:** existing Card Detail page in `site.py`

New display fields sourced from `DataService.get_card_detail()`:
- `sample_size` — "Based on 47 sales"
- `match_confidence` — colored badge (≥90% green, ≥70% yellow, <70% red)
- `data_age` — "Updated 3 hours ago"
- `source_breakdown` — "70% eBay, 30% TCG" bar

Price history chart upgrade:
- Free: 7-day window
- Pro: 180-day window
- Show confidence band if `match_confidence` available
- Data quality indicator on low-sample cards

**New template macro:** `templates/macros/pro_gate.html`

```jinja
{% macro render_pro_gate(config) %}
  {% if config.is_locked %}
    <div class="pro-gate-overlay">
      <div class="pro-gate-blur">{{ caller() }}</div>
      <div class="pro-gate-cta pro-gate-{{ config.urgency }}">
        <h4>{{ config.feature_name }}</h4>
        <p>{{ config.upgrade_reason }}</p>
        <a href="/upgrade" class="cta-btn">Upgrade to Pro</a>
      </div>
    </div>
  {% else %}
    {{ caller() }}
  {% endif %}
{% endmacro %}
```

Usage:
```jinja
{% call render_pro_gate(price_history_gate_config) %}
  <canvas id="price-chart"></canvas>
{% endcall %}
```

### B2: Source Comparison + CTA System (depends on B1)

**New routes in `site.py`:**
- `GET /cards/<card_id>/sources` — eBay vs TCG detailed comparison
  - Free: summary row only
  - Pro: full table with spread, AI recommendation
- `GET /cards/<card_id>/history` — standalone price history page (for Discord deep links)

**CTA strategy matrix** lives entirely in `get_pro_gate_config()` in `core/permissions.py`. No hardcoded CTA strings in templates.

**Urgency rendering:**

| urgency | CSS class | CTA button color | Bot emoji prefix |
|---|---|---|---|
| `high` | `pro-gate-high` | `#FF4444`, pulse animation | 🔥 |
| `medium` | `pro-gate-medium` | `#FF8800`, no animation | 📈 |
| `low` | `pro-gate-low` | `#888888`, no animation | 💡 |

### Completion Criteria

- [ ] Card Detail shows sample_size, match_confidence badge, source_breakdown
- [ ] Price chart respects Free 7-day / Pro 180-day window
- [ ] `pro_gate.html` macro renders blur overlay + CTA on locked features
- [ ] `/cards/<id>/sources` page live with Free/Pro gating
- [ ] No CTA strings hardcoded in templates

---

## Phase C: Discord Traffic Funnel (depends on Phase B)

### Layer 1: Direct Links (deployable before Phase B)

All 9 Bot slash commands add a `url` field to their embed using `make_web_link()`.

**`bot/link_builder.py`** (new file):

```python
def make_web_link(path: str, source_context: dict) -> str:
    params = {
        "utm_source": "discord",
        "utm_medium": source_context["command_type"],   # slash_command | price_alert | daily_summary
        "utm_campaign": source_context["campaign"],     # card_discovery | pro_conversion | engagement
        "from": "discord",
    }
    if source_context.get("signal_type"):
        params["utm_content"] = source_context["signal_type"]   # BREAKOUT | MOVE | WATCH
    if source_context.get("card_id"):
        params["ref"] = source_context["card_id"]
    if source_context.get("user_tier"):
        params["tier"] = source_context["user_tier"]    # free | pro

    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{BASE_URL}{path}?{qs}"
```

### Layer 2: DataService-powered replies (after Phase B1)

Bot slash commands switch from direct API calls to `DataService`. `ResponseTemplates.price_alert()` enhanced in-place:

```python
class ResponseTemplates:
    @staticmethod
    def price_alert(card_data) -> dict:
        base_desc = f"Price moved {card_data.change}%"
        enhancements = []

        if getattr(card_data, "sample_size", None):
            enhancements.append(f"📊 Based on {card_data.sample_size} sales")

        if getattr(card_data, "match_confidence", None):
            icon = "✅" if card_data.match_confidence >= 90 else "⚠️"
            enhancements.append(f"{icon} {card_data.match_confidence}% confident")

        if card_data.pro_gate_config and card_data.pro_gate_config.is_locked:
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

Single method. Phase B2 completion: add `source_breakdown` block directly — no versioning needed.

### Layer 3: Discord-specific landing pages (new routes in `site.py`)

Three new routes:

```python
@app.route("/welcome-from-discord")
def discord_welcome():
    if current_user.is_authenticated:
        ref = request.args.get("ref")
        return redirect(f"/cards/{ref}?from=discord" if ref else "/dashboard?from=discord")
    return render_template("discord/welcome.html", utm_data=extract_utm_params(request))

@app.route("/upgrade-from-discord")
def discord_upgrade():
    if not current_user.is_authenticated:
        return redirect(url_for("login", next=url_for("discord_upgrade")))
    if current_user.access_tier == "pro":
        return redirect("/signals?from=discord")
    return render_template("discord/upgrade.html", user=current_user,
                           utm_data=extract_utm_params(request))

@app.route("/signals/explained")
def signals_explained():
    return render_template("discord/signals_explained.html")
```

Templates: `templates/discord/welcome.html`, `templates/discord/upgrade.html`, `templates/discord/signals_explained.html`

### Conversion Tracking Targets

| Funnel step | Metric |
|---|---|
| Layer 1 | Discord embed link click-through rate |
| Layer 2 | Web engagement rate after Discord arrival |
| Layer 3 | Discord → registration, Discord → Pro upgrade |

**UTM data storage decision:** No custom DB table. Server access logs capture all UTM params. Parse logs or pipe to an analytics tool once baseline data exists. Building a `utm_tracking` table before having baseline numbers is premature — defer until Phase C has been live for 2+ weeks.

### Completion Criteria

- [ ] All 9 Bot commands include UTM-tagged web link
- [ ] `ResponseTemplates.price_alert()` shows credibility data when available
- [ ] `/welcome-from-discord`, `/upgrade-from-discord`, `/signals/explained` live
- [ ] `extract_utm_params()` utility available in `site.py`
- [ ] `make_web_link()` used everywhere in Bot — no hardcoded URLs

---

## Dependency Chain

```
Phase A complete
    └── Phase B1 (Card Detail credibility + ProGate)
            └── Phase B2 (Source Comparison + /cards/<id>/sources)
                    └── Phase C Layer 2 (Bot uses DataService data)
                            └── Phase C Layer 3 (landing pages)

Phase C Layer 1 (direct links) — independent, can ship with Phase A
```

---

## What Is NOT Changing

- `site.py` existing routes — untouched
- `services/`, `models/`, `api/routes/` — untouched  
- Existing Bot commands logic — only embed format changes
- Existing permission enum values in `core/permissions.py`
- A/B testing infrastructure — deferred (no baseline data yet)
- Feature flags for Bot response versions — not needed; direct replacement used
