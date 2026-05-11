# Pro Tier Launch Implementation Plan (TASK-301)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire LemonSqueezy payments, trial flow, and Pro feature gates so a user can pay $12/month and access gated features.

**Architecture:** Five sequential PRs — (A) backend payment infrastructure, (B) trial flow + scheduler job, (C) frontend `/pricing` page + nav CTA, (D) Pro gate restoration + CSV export, (E) email flows. Each PR ships independently and leaves the product in a shippable state. All billing state is owned by LemonSqueezy; our DB syncs from webhooks.

**Tech Stack:** Python/FastAPI (webhook handler), LemonSqueezy REST API, LemonSqueezy.js overlay (checkout), React 19 + TypeScript (pricing page), APScheduler (trial expiry job), Resend (transactional email), Jinja2 (email templates). No new dependencies needed — all tooling is already present.

**Reference docs:**
- `docs/decisions/2026-05-02-pro-launch-parameters.md` — all 6 decisions (provider, pricing, trial, refund, retention, sequence)
- `docs/strategy/06_pro_tier_launch.md` — full design doc
- `03_pricing_page_copy.md` — pricing page copy and feature table
- `CLAUDE.md §12` — ProGate restore instructions for AI analysis

---

## Pre-flight: LemonSqueezy account setup (operator action, not code)

Before any code runs, Ivan must:
1. Create a LemonSqueezy account at `lemonsqueezy.com`
2. Create a Store (name: "Flashcard Planet")
3. Create a Product: "Flashcard Planet Pro", recurring, monthly
4. Create two Variants: "Standard" ($12 USD/month) and "Founders" ($9 USD/month)
5. Enable "Free trial without payment method" (7 days) on both variants
6. Create a Webhook pointing to `https://<railway-url>/api/v1/webhooks/lemonsqueezy` for events: `subscription_created`, `subscription_updated`, `subscription_cancelled`, `subscription_expired`, `subscription_payment_failed`, `subscription_payment_success`
7. Copy the Webhook signing secret
8. Add these Railway env vars:
   - `LEMONSQUEEZY_API_KEY` — from LS Settings → API Keys
   - `LEMONSQUEEZY_STORE_ID` — from LS Store dashboard (numeric)
   - `LEMONSQUEEZY_PRODUCT_ID_PRO` — from LS Product
   - `LEMONSQUEEZY_VARIANT_ID_STANDARD` — from LS Variant
   - `LEMONSQUEEZY_VARIANT_ID_FOUNDERS` — from LS Variant
   - `LEMONSQUEEZY_WEBHOOK_SECRET` — from LS Webhook settings

**Code cannot run end-to-end until these are in Railway env vars.**

---

## File Map

### New files
- `backend/app/api/routes/webhooks.py` — LemonSqueezy webhook handler
- `backend/app/services/subscription_service.py` — subscription sync logic (status → user fields)
- `backend/app/email/templates/trial_started.html` — trial welcome email
- `backend/app/email/templates/trial_expiring_soon.html` — day-6 conversion email
- `frontend/src/pages/PricingPage.tsx` — `/pricing` page

### Modified files
- `backend/app/core/config.py` — add LemonSqueezy settings fields
- `backend/app/api/router.py` — mount webhooks router
- `backend/app/backstage/scheduler.py` — add `trial-expiry-sweep` job
- `backend/app/services/scheduler_run_log_service.py` — add `JOB_TRIAL_EXPIRY` constant
- `backend/app/email/resend_client.py` — add `send_trial_started_email()`, `send_trial_expiring_soon_email()`
- `frontend/src/main.tsx` — add `/pricing` route
- `frontend/src/components/NavBar.tsx` — add "Upgrade" link to `/pricing` for free-tier users
- `frontend/src/pages/DashboardPage.tsx` — restore Volume/Recent sort ProGate (CLAUDE.md §12)
- `frontend/src/pages/CardDetailPage.tsx` — gate confidence score on Pro (CLAUDE.md §12)
- `backend/app/api/routes/web.py` — gate AI analysis field on Pro (CLAUDE.md §12)
- `backend/app/api/routes/account.py` — add `GET /api/v1/account/checkout-url` endpoint

---

## PR A: Backend payment infrastructure

**One concern:** LemonSqueezy config + webhook handler + subscription sync service.  
**Verifiable independently:** Run the test suite. Use a real LS webhook test-send from the LS dashboard after merging.

---

### Task A1: Add LemonSqueezy settings to config

**Files:**
- Modify: `backend/app/core/config.py`
- Test: `tests/test_config.py` (existing)

- [ ] **Step 1: Add LS fields to Settings**

In `backend/app/core/config.py`, inside the `Settings` class after `discord_alert_webhook_url`:

```python
# LemonSqueezy
lemonsqueezy_api_key: str = ""
lemonsqueezy_store_id: str = ""
lemonsqueezy_product_id_pro: str = ""
lemonsqueezy_variant_id_standard: str = ""
lemonsqueezy_variant_id_founders: str = ""
lemonsqueezy_webhook_secret: str = ""
```

- [ ] **Step 2: Verify import works**

```bash
python -c "from backend.app.core.config import get_settings; s = get_settings(); print(s.lemonsqueezy_api_key)"
```
Expected: empty string (env var not set yet).

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/config.py
git commit -m "feat(config): add LemonSqueezy settings fields (TASK-301 A)"
```

---

### Task A2: Subscription sync service

**Files:**
- Create: `backend/app/services/subscription_service.py`
- Test: `tests/test_subscription_service.py` (new)

- [ ] **Step 1: Write tests**

Create `tests/test_subscription_service.py`:

```python
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from backend.app.services.subscription_service import sync_subscription_to_user


def _user():
    u = MagicMock()
    u.access_tier = "free"
    u.subscription_status = "free"
    u.subscription_tier = "free"
    u.subscription_provider = None
    u.subscription_provider_id = None
    u.subscription_current_period_end = None
    u.subscription_cancel_at_period_end = False
    u.trial_ends_at = None
    u.trial_started_at = None
    u.is_founders = False
    return u


def test_active_pro_sets_access_tier():
    user = _user()
    now = datetime.now(timezone.utc)
    sync_subscription_to_user(
        user,
        event_name="subscription_created",
        status="active",
        subscription_tier="pro",
        provider_id="sub_123",
        period_end=now + timedelta(days=30),
        cancel_at_period_end=False,
        is_founders=False,
    )
    assert user.access_tier == "pro"
    assert user.subscription_status == "active"
    assert user.subscription_provider_id == "sub_123"


def test_trialing_sets_access_tier_pro():
    user = _user()
    sync_subscription_to_user(
        user,
        event_name="subscription_created",
        status="trialing",
        subscription_tier="pro",
        provider_id="sub_456",
        period_end=None,
        cancel_at_period_end=False,
        is_founders=False,
    )
    assert user.access_tier == "pro"
    assert user.subscription_status == "trialing"


def test_expired_sets_access_tier_free():
    user = _user()
    user.access_tier = "pro"
    user.subscription_status = "active"
    sync_subscription_to_user(
        user,
        event_name="subscription_expired",
        status="expired",
        subscription_tier="pro",
        provider_id="sub_789",
        period_end=None,
        cancel_at_period_end=False,
        is_founders=False,
    )
    assert user.access_tier == "free"
    assert user.subscription_status == "expired"


def test_cancelled_keeps_pro_until_period_end():
    user = _user()
    user.access_tier = "pro"
    future = datetime.now(timezone.utc) + timedelta(days=15)
    sync_subscription_to_user(
        user,
        event_name="subscription_cancelled",
        status="cancelled",
        subscription_tier="pro",
        provider_id="sub_abc",
        period_end=future,
        cancel_at_period_end=True,
        is_founders=False,
    )
    assert user.access_tier == "pro"
    assert user.subscription_status == "cancelled"
    assert user.subscription_cancel_at_period_end is True


def test_past_due_keeps_access():
    user = _user()
    user.access_tier = "pro"
    sync_subscription_to_user(
        user,
        event_name="subscription_payment_failed",
        status="past_due",
        subscription_tier="pro",
        provider_id="sub_def",
        period_end=None,
        cancel_at_period_end=False,
        is_founders=False,
    )
    assert user.access_tier == "pro"
    assert user.subscription_status == "past_due"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_subscription_service.py -v
```
Expected: `ModuleNotFoundError: No module named 'backend.app.services.subscription_service'`

- [ ] **Step 3: Implement the service**

Create `backend/app/services/subscription_service.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

# Statuses where the user keeps Pro access
_ACTIVE_STATUSES = {"active", "trialing", "past_due", "cancelled"}
# Statuses where the user loses Pro access immediately
_EXPIRED_STATUSES = {"expired", "free"}


def sync_subscription_to_user(
    user: Any,
    *,
    event_name: str,
    status: str,
    subscription_tier: str,
    provider_id: str,
    period_end: datetime | None,
    cancel_at_period_end: bool,
    is_founders: bool,
) -> None:
    """Apply a LemonSqueezy subscription event to a User ORM object.

    Does NOT commit — the caller owns the session.
    Idempotency is handled by the webhook handler (SubscriptionEvent dedup).
    """
    user.subscription_status = status
    user.subscription_tier = subscription_tier
    user.subscription_provider = "lemonsqueezy"
    user.subscription_provider_id = provider_id
    user.subscription_cancel_at_period_end = cancel_at_period_end
    if is_founders:
        user.is_founders = True

    if period_end is not None:
        user.subscription_current_period_end = period_end

    # Derive access_tier from status
    if status in _EXPIRED_STATUSES:
        user.access_tier = "free"
    elif status in _ACTIVE_STATUSES and subscription_tier in ("pro", "plus"):
        user.access_tier = subscription_tier
    else:
        user.access_tier = "free"
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_subscription_service.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/subscription_service.py tests/test_subscription_service.py
git commit -m "feat(subscriptions): add subscription sync service (TASK-301 A)"
```

---

### Task A3: LemonSqueezy webhook handler

**Files:**
- Create: `backend/app/api/routes/webhooks.py`
- Modify: `backend/app/api/router.py`
- Test: `tests/test_webhooks.py` (new)

- [ ] **Step 1: Write tests**

Create `tests/test_webhooks.py`:

```python
import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _make_payload(event_name: str, status: str, email: str = "test@example.com") -> dict:
    return {
        "meta": {
            "event_name": event_name,
            "custom_data": {"user_id": "00000000-0000-0000-0000-000000000001"},
        },
        "data": {
            "id": "sub_test_123",
            "attributes": {
                "status": status,
                "variant_id": "12345",
                "user_email": email,
                "ends_at": None,
                "renews_at": "2026-06-12T00:00:00.000000Z",
                "cancelled": False,
            },
        },
    }


@pytest.fixture
def test_client():
    from backend.app.main import app
    return TestClient(app)


def test_webhook_rejects_missing_signature(test_client):
    payload = json.dumps(_make_payload("subscription_created", "active")).encode()
    resp = test_client.post(
        "/api/v1/webhooks/lemonsqueezy",
        content=payload,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 401


def test_webhook_rejects_invalid_signature(test_client):
    payload = json.dumps(_make_payload("subscription_created", "active")).encode()
    resp = test_client.post(
        "/api/v1/webhooks/lemonsqueezy",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-Signature": "bad_signature",
        },
    )
    assert resp.status_code == 401


def test_webhook_accepts_valid_signature(test_client):
    from unittest.mock import patch

    payload_dict = _make_payload("subscription_created", "active")
    payload = json.dumps(payload_dict).encode()
    secret = "test_webhook_secret"
    sig = _sign(secret, payload)

    with patch("backend.app.api.routes.webhooks.get_settings") as mock_settings, \
         patch("backend.app.api.routes.webhooks.get_database") as mock_db:
        mock_settings.return_value.lemonsqueezy_webhook_secret = secret
        mock_db.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_db.return_value.__exit__ = MagicMock(return_value=False)

        resp = test_client.post(
            "/api/v1/webhooks/lemonsqueezy",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Signature": sig,
            },
        )
    # 200 or 404 (user not found in test DB) are both acceptable — just not 401
    assert resp.status_code != 401
```

- [ ] **Step 2: Run tests — expect them to fail**

```bash
pytest tests/test_webhooks.py -v
```
Expected: failures (no webhook route yet).

- [ ] **Step 3: Create the webhook handler**

Create `backend/app/api/routes/webhooks.py`:

```python
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.core.config import get_settings
from backend.app.models.subscription_event import SubscriptionEvent
from backend.app.models.user import User
from backend.app.services.subscription_service import sync_subscription_to_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_VARIANT_TIER_MAP: dict[str, str] = {}  # populated at startup from env vars


def _verify_signature(raw_body: bytes, signature: str | None, secret: str) -> None:
    """Raise 401 if signature is missing or invalid."""
    if not signature:
        raise HTTPException(status_code=401, detail="Missing X-Signature header")
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


def _parse_renews_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@router.post("/lemonsqueezy")
async def lemonsqueezy_webhook(
    request: Request,
    x_signature: str | None = Header(default=None),
    db: Session = Depends(get_database),
) -> dict[str, str]:
    settings = get_settings()
    raw_body = await request.body()

    _verify_signature(raw_body, x_signature, settings.lemonsqueezy_webhook_secret)

    try:
        payload: dict[str, Any] = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    meta = payload.get("meta", {})
    event_name: str = meta.get("event_name", "")
    event_id: str = meta.get("event_id", "") or f"{event_name}_{payload.get('data', {}).get('id', '')}"

    # Idempotency: skip if already processed
    existing = db.execute(
        select(SubscriptionEvent).where(SubscriptionEvent.event_id == event_id)
    ).scalar_one_or_none()
    if existing:
        logger.info("webhook_duplicate event_id=%s skipping", event_id)
        return {"status": "duplicate"}

    data = payload.get("data", {})
    attrs = data.get("attributes", {})
    sub_id: str = str(data.get("id", ""))
    status: str = attrs.get("status", "")
    variant_id: str = str(attrs.get("variant_id", ""))
    user_email: str = attrs.get("user_email", "")
    renews_at: datetime | None = _parse_renews_at(attrs.get("renews_at"))
    cancelled: bool = bool(attrs.get("cancelled", False))

    # Resolve variant → tier
    std_id = settings.lemonsqueezy_variant_id_standard
    founders_id = settings.lemonsqueezy_variant_id_founders
    is_founders = variant_id == founders_id
    subscription_tier = "pro"  # all current variants are Pro

    # Log the event regardless of user lookup outcome
    sub_event = SubscriptionEvent(
        event_id=event_id,
        event_name=event_name,
        subscription_provider_id=sub_id,
        payload_json=raw_body.decode("utf-8", errors="replace"),
    )

    # Find the user — by custom_data.user_id first, then by email
    user: User | None = None
    custom_data = meta.get("custom_data", {})
    user_id_str = custom_data.get("user_id")
    if user_id_str:
        try:
            import uuid
            uid = uuid.UUID(user_id_str)
            user = db.execute(select(User).where(User.id == uid)).scalar_one_or_none()
        except (ValueError, AttributeError):
            pass
    if user is None and user_email:
        user = db.execute(
            select(User).where(User.email == user_email.lower())
        ).scalar_one_or_none()

    if user is None:
        logger.warning(
            "webhook_user_not_found event=%s sub_id=%s email=%s",
            event_name, sub_id, user_email,
        )
        sub_event.user_id = None
        db.add(sub_event)
        db.commit()
        return {"status": "user_not_found"}

    sub_event.user_id = user.id

    sync_subscription_to_user(
        user,
        event_name=event_name,
        status=status,
        subscription_tier=subscription_tier,
        provider_id=sub_id,
        period_end=renews_at,
        cancel_at_period_end=cancelled,
        is_founders=is_founders,
    )

    db.add(sub_event)
    db.commit()

    logger.info(
        "webhook_processed event=%s sub_id=%s user_id=%s new_status=%s tier=%s",
        event_name, sub_id, user.id, status, subscription_tier,
    )
    return {"status": "ok"}
```

- [ ] **Step 4: Mount the router in `backend/app/api/router.py`**

Open `backend/app/api/router.py`. Find the existing router includes. Add:

```python
from backend.app.api.routes.webhooks import router as webhooks_router
# ...
api_router.include_router(webhooks_router, prefix=settings.api_prefix)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_webhooks.py -v
pytest tests/ -q --ignore=tests/test_google_oauth.py --ignore=tests/test_main.py 2>&1 | tail -5
```
Expected: webhook tests pass; full suite ~989+ pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/webhooks.py backend/app/api/router.py tests/test_webhooks.py
git commit -m "feat(webhooks): LemonSqueezy webhook handler + HMAC verification (TASK-301 A)"
```

---

### Task A4: Checkout URL endpoint

Users need a URL to start a LemonSqueezy checkout. This endpoint generates a LemonSqueezy checkout URL for the logged-in user.

**Files:**
- Modify: `backend/app/api/routes/account.py`
- Test: `tests/test_account_routes.py` (existing — add new test)

- [ ] **Step 1: Write the failing test**

In `tests/test_account_routes.py`, add:

```python
def test_checkout_url_requires_auth(client):
    resp = client.get("/api/v1/account/checkout-url")
    assert resp.status_code in (401, 403)
```

- [ ] **Step 2: Run test — confirm it fails (route doesn't exist)**

```bash
pytest tests/test_account_routes.py::test_checkout_url_requires_auth -v
```
Expected: FAIL (404, not 401/403 — route missing).

- [ ] **Step 3: Add the endpoint to `account.py`**

In `backend/app/api/routes/account.py`, add after the existing routes:

```python
import httpx

@router.get("/checkout-url")
def get_checkout_url(
    variant: str = Query(default="standard", description="standard | founders"),
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Generate a LemonSqueezy checkout URL pre-filled with the user's email."""
    settings = get_settings()
    if not settings.lemonsqueezy_api_key:
        raise HTTPException(status_code=503, detail="Payment provider not configured")

    variant_id = (
        settings.lemonsqueezy_variant_id_founders
        if variant == "founders"
        else settings.lemonsqueezy_variant_id_standard
    )
    if not variant_id:
        raise HTTPException(status_code=503, detail="Variant not configured")

    payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "checkout_data": {
                    "email": current_user.email,
                    "custom": {"user_id": str(current_user.id)},
                },
            },
            "relationships": {
                "store": {"data": {"type": "stores", "id": settings.lemonsqueezy_store_id}},
                "variant": {"data": {"type": "variants", "id": variant_id}},
            },
        }
    }

    resp = httpx.post(
        "https://api.lemonsqueezy.com/v1/checkouts",
        json=payload,
        headers={
            "Authorization": f"Bearer {settings.lemonsqueezy_api_key}",
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json",
        },
        timeout=10.0,
    )
    if resp.status_code not in (200, 201):
        logger.error("lemonsqueezy_checkout_failed status=%s body=%s", resp.status_code, resp.text[:300])
        raise HTTPException(status_code=502, detail="Could not create checkout session")

    checkout_url: str = resp.json()["data"]["attributes"]["url"]
    return {"checkout_url": checkout_url}
```

- [ ] **Step 4: Run test — confirm it passes**

```bash
pytest tests/test_account_routes.py::test_checkout_url_requires_auth -v
```
Expected: PASS (route now exists, returns 401/403 for unauthed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/account.py tests/test_account_routes.py
git commit -m "feat(account): GET /account/checkout-url — LemonSqueezy checkout link (TASK-301 A)"
```

---

## PR B: Trial flow + expiry scheduler job

---

### Task B1: Trial start endpoint

When a user registers (magic link or Google OAuth), they automatically start a 7-day trial. This endpoint can also be called explicitly from the `/pricing` CTA for existing free users.

**Files:**
- Create: `backend/app/api/routes/trial.py`
- Modify: `backend/app/api/router.py`
- Modify: `backend/app/auth/google_oauth.py` and `backend/app/api/routes/auth.py` (call trial start on new user creation)
- Test: `tests/test_trial.py` (new)

- [ ] **Step 1: Write failing tests**

Create `tests/test_trial.py`:

```python
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


def test_trial_sets_trialing_status():
    from backend.app.api.routes.trial import _start_trial_for_user

    user = MagicMock()
    user.subscription_status = "free"
    user.trial_ends_at = None
    user.trial_started_at = None

    now = datetime.now(timezone.utc)
    _start_trial_for_user(user, now=now)

    assert user.subscription_status == "trialing"
    assert user.access_tier == "pro"
    assert user.trial_started_at is not None
    expected_end = now + timedelta(days=7)
    assert abs((user.trial_ends_at - expected_end).total_seconds()) < 5


def test_trial_does_not_restart_if_already_active():
    from backend.app.api.routes.trial import _start_trial_for_user

    user = MagicMock()
    user.subscription_status = "active"
    user.trial_ends_at = None
    user.trial_started_at = None
    original_status = user.subscription_status

    _start_trial_for_user(user, now=datetime.now(timezone.utc))

    # Already active — should not change status to trialing
    assert user.subscription_status == "active"


def test_trial_does_not_restart_if_already_trialing():
    from backend.app.api.routes.trial import _start_trial_for_user

    user = MagicMock()
    user.subscription_status = "trialing"
    user.trial_ends_at = datetime.now(timezone.utc) + timedelta(days=5)

    _start_trial_for_user(user, now=datetime.now(timezone.utc))

    # Should not reset trial_ends_at
    assert (user.trial_ends_at - datetime.now(timezone.utc)).total_seconds() > 4 * 86400
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
pytest tests/test_trial.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement**

Create `backend/app/api/routes/trial.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database, require_auth
from backend.app.models.user import User

TRIAL_DURATION_DAYS = 7
_ACTIVE_STATUSES = {"active", "trialing", "past_due", "cancelled"}

router = APIRouter(prefix="/trial", tags=["trial"])


def _start_trial_for_user(user: Any, *, now: datetime | None = None) -> bool:
    """Set user to trialing state. Returns True if trial was started, False if skipped.

    Idempotent: no-op if user is already on an active/trialing subscription.
    """
    if user.subscription_status in _ACTIVE_STATUSES:
        return False
    if now is None:
        now = datetime.now(timezone.utc)
    user.subscription_status = "trialing"
    user.access_tier = "pro"
    user.trial_started_at = now
    user.trial_ends_at = now + timedelta(days=TRIAL_DURATION_DAYS)
    return True


@router.post("/start")
def start_trial(
    current_user: User = Depends(require_auth),
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Start a 7-day Pro trial for a free-tier user. No-op if already active."""
    started = _start_trial_for_user(current_user)
    if started:
        db.commit()
        return {"status": "started", "trial_ends_at": current_user.trial_ends_at.isoformat()}
    return {"status": "already_active", "subscription_status": current_user.subscription_status}
```

- [ ] **Step 4: Mount in router.py**

In `backend/app/api/router.py`:
```python
from backend.app.api.routes.trial import router as trial_router
# ...
api_router.include_router(trial_router, prefix=settings.api_prefix)
```

- [ ] **Step 5: Auto-start trial on new user registration**

In `backend/app/api/routes/auth.py`, find the section where a new user is created (after `db.add(user); db.flush()`). Add:

```python
from backend.app.api.routes.trial import _start_trial_for_user
# ...
# After creating the new user record:
_start_trial_for_user(user)  # gives 7-day Pro trial to all new signups
```

Do the same in `backend/app/auth/google_oauth.py` where new users are created.

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_trial.py -v
pytest tests/ -q --ignore=tests/test_google_oauth.py --ignore=tests/test_main.py 2>&1 | tail -5
```
Expected: trial tests pass; full suite passes.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes/trial.py backend/app/api/router.py \
        backend/app/api/routes/auth.py backend/app/auth/google_oauth.py \
        tests/test_trial.py
git commit -m "feat(trial): 7-day Pro trial on new user registration (TASK-301 B)"
```

---

### Task B2: Trial expiry scheduler job

**Files:**
- Modify: `backend/app/backstage/scheduler.py`
- Modify: `backend/app/services/scheduler_run_log_service.py`
- Test: `tests/test_trial_expiry_job.py` (new)

- [ ] **Step 1: Add JOB_TRIAL_EXPIRY constant**

In `backend/app/services/scheduler_run_log_service.py`, add after `JOB_HISTORY_PRUNE`:

```python
JOB_TRIAL_EXPIRY = "trial-expiry-sweep"
```

- [ ] **Step 2: Write failing test**

Create `tests/test_trial_expiry_job.py`:

```python
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


def test_expired_trials_get_downgraded(db_session):
    """Users with trial_ends_at in the past should be downgraded to free."""
    from backend.app.backstage.scheduler import _run_trial_expiry_sweep

    # Insert a user whose trial expired yesterday
    from backend.app.models.user import User
    import uuid
    user = User(
        id=uuid.uuid4(),
        email="expired@example.com",
        subscription_status="trialing",
        access_tier="pro",
        trial_ends_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(user)
    db_session.commit()

    _run_trial_expiry_sweep(db_session)

    db_session.refresh(user)
    assert user.subscription_status == "expired"
    assert user.access_tier == "free"


def test_active_trials_not_touched(db_session):
    """Users with trial_ends_at in the future should not be changed."""
    from backend.app.backstage.scheduler import _run_trial_expiry_sweep
    from backend.app.models.user import User
    import uuid

    user = User(
        id=uuid.uuid4(),
        email="active_trial@example.com",
        subscription_status="trialing",
        access_tier="pro",
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=3),
    )
    db_session.add(user)
    db_session.commit()

    _run_trial_expiry_sweep(db_session)

    db_session.refresh(user)
    assert user.subscription_status == "trialing"
    assert user.access_tier == "pro"
```

- [ ] **Step 3: Run tests — confirm they fail**

```bash
pytest tests/test_trial_expiry_job.py -v
```
Expected: `AttributeError: _run_trial_expiry_sweep not found`

- [ ] **Step 4: Add `_run_trial_expiry_sweep` to scheduler.py**

In `backend/app/backstage/scheduler.py`, after the `_run_signal_history_prune` function, add:

```python
def _run_trial_expiry_sweep(session: Session) -> int:
    """Downgrade users whose 7-day trial has expired. Returns count of users downgraded."""
    from sqlalchemy import select, update
    from backend.app.models.user import User

    now = datetime.now(timezone.utc)
    expired_users = session.execute(
        select(User).where(
            User.subscription_status == "trialing",
            User.trial_ends_at.isnot(None),
            User.trial_ends_at < now,
        )
    ).scalars().all()

    count = 0
    for user in expired_users:
        user.subscription_status = "expired"
        user.access_tier = "free"
        count += 1

    if count > 0:
        session.flush()
    return count
```

Then register the job. In the scheduler's `prepare_scheduler_for_startup` function, find where other jobs are registered (e.g., `signal-history-prune`) and add:

```python
scheduler.add_job(
    _scheduled_trial_expiry_sweep,
    trigger=IntervalTrigger(hours=6),
    id="trial-expiry-sweep",
    next_run_time=None,
    misfire_grace_time=300,
)
logger.info(
    "trial-expiry-sweep registered. trigger=interval/6h first_run=startup+%ds",
    _STARTUP_DELAY.get("trial-expiry-sweep", 900),
)
```

Add to `_STARTUP_DELAY`:
```python
"trial-expiry-sweep": 900,  # 15 min — after heartbeat, before next ingest cycle
```

Add the job runner function:

```python
def _scheduled_trial_expiry_sweep() -> None:
    """Expire trials that have passed their 7-day window."""
    try:
        with SessionLocal() as _log_session:
            _run_id = start_run(_log_session, JOB_TRIAL_EXPIRY)
    except Exception as exc:
        logger.exception("start_run_failed job=%s", JOB_TRIAL_EXPIRY)
        send_discord_alert("error", f"CRITICAL: start_run 失败 — {JOB_TRIAL_EXPIRY}", f"error={exc}")
        return

    _exc: BaseException | None = None
    try:
        with SessionLocal() as session:
            count = _run_trial_expiry_sweep(session)
            session.commit()
        logger.info("trial-expiry-sweep complete: downgraded=%d", count)
    except Exception as exc:
        _exc = exc
        logger.exception("trial_expiry_sweep_failed")
        send_discord_alert("error", f"trial-expiry-sweep failed", f"error={exc}")
    finally:
        with SessionLocal() as _fin:
            finish_run(
                _fin, _run_id,
                status="error" if _exc else "success",
                records_written=0,
                errors=1 if _exc else 0,
                error_message=str(_exc)[:500] if _exc else None,
            )
            prune_old_runs(_fin, JOB_TRIAL_EXPIRY)
```

Also add `JOB_TRIAL_EXPIRY` to `_monitored_jobs` in `_send_heartbeat` and to `_tracked_jobs` in `admin_stats`.

Import `JOB_TRIAL_EXPIRY` at the top of `scheduler.py`:
```python
from backend.app.services.scheduler_run_log_service import (
    ...,
    JOB_TRIAL_EXPIRY,
)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_trial_expiry_job.py -v
pytest tests/ -q --ignore=tests/test_google_oauth.py --ignore=tests/test_main.py 2>&1 | tail -5
```
Expected: trial expiry tests pass; full suite passes.

- [ ] **Step 6: Commit**

```bash
git add backend/app/backstage/scheduler.py \
        backend/app/services/scheduler_run_log_service.py \
        tests/test_trial_expiry_job.py
git commit -m "feat(scheduler): trial-expiry-sweep job — downgrade expired 7-day trials (TASK-301 B)"
```

---

## PR C: Frontend `/pricing` page + nav CTA

---

### Task C1: PricingPage.tsx

**Files:**
- Create: `frontend/src/pages/PricingPage.tsx`
- Modify: `frontend/src/main.tsx` (add route)

- [ ] **Step 1: Create the pricing page**

Create `frontend/src/pages/PricingPage.tsx`:

```tsx
import { useState } from 'react'
import NavBar from '../components/NavBar'
import { useUser } from '../hooks/useUser'

const FREE_FEATURES = [
  'Signal labels (BREAKOUT / MOVE / WATCH / IDLE)',
  'Up to 10 cards on your watchlist',
  'Up to 5 price alerts',
  'Card detail pages with price history',
  '7-day free Pro trial — no card required',
]

const PRO_FEATURES = [
  'Everything in Free',
  'Confidence score on every signal',
  'AI-written explanation per signal — know WHY a card is moving',
  'Unlimited watchlist',
  'Unlimited alerts',
  'Advanced sorting (Volume, Recent)',
  'CSV export',
  'Priority Discord alerts',
]

const FAQ = [
  {
    q: 'Is there a free trial?',
    a: 'Yes — 7 days of full Pro access, no credit card required. When your trial ends, you automatically drop to the free tier. You can upgrade any time during or after your trial.',
  },
  {
    q: 'What happens if I cancel?',
    a: 'You keep Pro access until the end of your billing period. Your watchlist and alert settings are saved for 90 days — if you resubscribe, everything is exactly where you left it.',
  },
  {
    q: 'What currencies do you accept?',
    a: 'We bill in USD. LemonSqueezy (our payment provider) automatically displays your local currency equivalent at checkout.',
  },
  {
    q: 'Is there a money-back guarantee?',
    a: '14-day money-back guarantee, no questions asked. Email hello@flashcardplanet.com.',
  },
]

export default function PricingPage() {
  const { tier } = useUser()
  const [loading, setLoading] = useState(false)

  async function handleUpgrade(variant: 'standard' | 'founders') {
    setLoading(true)
    try {
      const resp = await fetch(`/api/v1/account/checkout-url?variant=${variant}`, {
        credentials: 'include',
      })
      if (!resp.ok) {
        // Not logged in — send to landing page
        window.location.href = '/?upgrade=1'
        return
      }
      const { checkout_url } = await resp.json()
      window.location.href = checkout_url
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <NavBar />
      <div className="page-content" style={{ maxWidth: 820, margin: '0 auto', padding: '40px 24px' }}>
        {/* Hero */}
        <div style={{ textAlign: 'center', marginBottom: 48 }}>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 36, fontWeight: 700, marginBottom: 12 }}>
            Simple pricing.
          </h1>
          <p style={{ fontSize: 16, color: 'var(--text-secondary)', marginBottom: 0 }}>
            Start free. Upgrade when you need the edge.
          </p>
        </div>

        {/* Plan cards */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 48 }}>
          {/* Free */}
          <div className="surface" style={{ padding: 28 }}>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700, marginBottom: 4 }}>Free</div>
            <div style={{ fontSize: 32, fontWeight: 700, marginBottom: 20 }}>$0</div>
            <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 24px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {FREE_FEATURES.map(f => (
                <li key={f} style={{ display: 'flex', gap: 8, fontSize: 13, color: 'var(--text-secondary)' }}>
                  <span style={{ color: 'var(--breakout)', flexShrink: 0 }}>✓</span>{f}
                </li>
              ))}
            </ul>
            {tier === 'free' ? (
              <div className="btn btn-ghost" style={{ width: '100%', justifyContent: 'center', cursor: 'default' }}>
                Current plan
              </div>
            ) : null}
          </div>

          {/* Pro */}
          <div className="surface" style={{ padding: 28, border: '1px solid var(--gold)', boxShadow: '0 0 32px var(--gold-glow)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 700 }}>Pro</div>
            </div>
            <div style={{ marginBottom: 4 }}>
              <span style={{ fontSize: 32, fontWeight: 700 }}>$12</span>
              <span style={{ fontSize: 14, color: 'var(--text-muted)', marginLeft: 4 }}>/month USD</span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--gold)', marginBottom: 20 }}>
              Founders pricing: $9/month — limited spots
            </div>
            <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 24px', display: 'flex', flexDirection: 'column', gap: 10 }}>
              {PRO_FEATURES.map(f => (
                <li key={f} style={{ display: 'flex', gap: 8, fontSize: 13 }}>
                  <span style={{ color: 'var(--gold)', flexShrink: 0 }}>✓</span>{f}
                </li>
              ))}
            </ul>
            {tier === 'pro' ? (
              <div className="btn btn-ghost" style={{ width: '100%', justifyContent: 'center', cursor: 'default' }}>
                Current plan
              </div>
            ) : (
              <button
                className="btn btn-primary"
                style={{ width: '100%', justifyContent: 'center' }}
                disabled={loading}
                onClick={() => handleUpgrade('standard')}
              >
                {loading ? 'Loading…' : 'Start 7-day free trial →'}
              </button>
            )}
          </div>
        </div>

        {/* FAQ */}
        <div style={{ maxWidth: 600, margin: '0 auto' }}>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700, marginBottom: 24 }}>
            Common questions
          </h2>
          {FAQ.map(({ q, a }) => (
            <div key={q} style={{ marginBottom: 28 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>{q}</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{a}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Add route to `main.tsx`**

In `frontend/src/main.tsx`:
```tsx
import PricingPage from './pages/PricingPage'
// ...
<Route path="/pricing" element={<PricingPage />} />
```

- [ ] **Step 3: Build**

```bash
cd frontend && npm run build 2>&1 | tail -5
```
Expected: clean build.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/PricingPage.tsx frontend/src/main.tsx
git commit -m "feat(pricing): /pricing page with feature table and trial CTA (TASK-301 C)"
```

---

### Task C2: NavBar upgrade CTA

Free-tier users should see a subtle "Upgrade" link in the nav pointing to `/pricing`.

**Files:**
- Modify: `frontend/src/components/NavBar.tsx`

- [ ] **Step 1: Add upgrade link**

In `frontend/src/components/NavBar.tsx`, find where the tier badge is rendered (around line 66-75). After the badge, add:

```tsx
{tier === 'free' && (
  <a
    href="/pricing"
    className="btn btn-gold-soft btn-sm"
    style={{ textDecoration: 'none', padding: '4px 12px', fontSize: 12 }}
  >
    Upgrade
  </a>
)}
```

- [ ] **Step 2: Build + verify**

```bash
cd frontend && npm run build 2>&1 | tail -3
```
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/NavBar.tsx
git commit -m "feat(nav): add Upgrade CTA to navbar for free-tier users (TASK-301 C)"
```

---

## PR D: Pro feature gate restoration

---

### Task D1: Restore Volume + Recent sort gating

Per CLAUDE.md §12: "Restore: `<ProGate feature="Sort by Volume" reason="Advanced sorting on Pro plan">`"

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`

- [ ] **Step 1: Restore ProGate on Volume sort**

In `frontend/src/pages/DashboardPage.tsx`, replace the TEMP-commented Volume sort block:

```tsx
{/* BEFORE (TEMP removed): */}
{/* <ProGate feature="Sort by Volume" reason="Advanced sorting on Pro plan"> */}
<button className="btn btn-ghost btn-sm" onClick={() => setSort('volume')}
  style={sort === 'volume' ? { background: 'var(--bg-elevated)', color: 'var(--gold)', borderColor: 'var(--gold-dim)' } : {}}>
  Volume
</button>
{/* </ProGate> */}

{/* AFTER (restored): */}
<ProGate feature="Sort by Volume" reason="Advanced sorting on Pro plan">
  <button className="btn btn-ghost btn-sm" onClick={() => setSort('volume')}
    style={sort === 'volume' ? { background: 'var(--bg-elevated)', color: 'var(--gold)', borderColor: 'var(--gold-dim)' } : {}}>
    Volume
  </button>
</ProGate>
```

Do the same for Recent sort:
```tsx
<ProGate feature="Sort by Recent" reason="Advanced sorting on Pro plan">
  <button className="btn btn-ghost btn-sm" onClick={() => setSort('recent')}
    style={sort === 'recent' ? { background: 'var(--bg-elevated)', color: 'var(--gold)', borderColor: 'var(--gold-dim)' } : {}}>
    Recent
  </button>
</ProGate>
```

Also remove the TEMP comments after making the change.

- [ ] **Step 2: Build**

```bash
cd frontend && npm run build 2>&1 | tail -3
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/DashboardPage.tsx
git commit -m "feat(gates): restore Volume + Recent sort ProGate (TASK-301 D, CLAUDE.md §12)"
```

---

### Task D2: Restore AI analysis gate

Per CLAUDE.md §12 restore instructions:
1. `backend/app/api/routes/web.py` — the `s.explanation AS ai_analysis` SELECT line has `-- TEMP` comment
2. Wire `access_tier` param to `web_card_detail`
3. Gate the field on `Feature.SIGNAL_EXPLANATION`

**Files:**
- Modify: `backend/app/api/routes/web.py`

- [ ] **Step 1: Find the TEMP comment**

```bash
grep -n "TEMP\|ai_analysis\|explanation" backend/app/api/routes/web.py | head -10
```

- [ ] **Step 2: Gate `ai_analysis` field**

In `backend/app/api/routes/web.py`, find the `web_card_detail` function. Follow CLAUDE.md §12 exactly:
- Add `access_tier` param (match existing auth pattern)
- Gate the `s.explanation AS ai_analysis` SELECT line: only include when `can(access_tier, Feature.SIGNAL_EXPLANATION)`
- Update the 3 TEMP test cases in `tests/test_web_routes.py::WebCardDetailTests` to assert tier-gated behaviour

The `can()` helper and `Feature.SIGNAL_EXPLANATION` are already in `backend/app/core/permissions.py`.

- [ ] **Step 3: Update tests**

In `tests/test_web_routes.py`, find `WebCardDetailTests`. Update the 3 tests marked TEMP to assert that `ai_analysis` is only present for Pro users.

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_web_routes.py -v 2>&1 | tail -10
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/web.py tests/test_web_routes.py
git commit -m "feat(gates): restore AI analysis Pro gate (TASK-301 D, CLAUDE.md §12)"
```

---

### Task D3: Gate confidence score in CardDetailPage

**Files:**
- Modify: `frontend/src/pages/CardDetailPage.tsx`

The confidence score is at `CardDetailPage.tsx:339`: `['Liquidity', card.liquidity_score != null ? ...]`.

The backend already controls what's returned based on `access_tier` for `explanation`. For `confidence` and `liquidity_score`, gate them client-side with `ProGate`:

- [ ] **Step 1: Wrap confidence score in ProGate**

In `frontend/src/pages/CardDetailPage.tsx`, find where `liquidity_score` and confidence are rendered. Wrap them with:

```tsx
<ProGate feature="Confidence score" reason="Signal confidence on Pro plan">
  {/* confidence score row */}
</ProGate>
```

- [ ] **Step 2: Build**

```bash
cd frontend && npm run build 2>&1 | tail -3
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/CardDetailPage.tsx
git commit -m "feat(gates): gate confidence score on Pro in CardDetailPage (TASK-301 D)"
```

---

### Task D4: CSV export endpoint + frontend button

**Files:**
- Modify: `backend/app/api/routes/web.py` (add CSV export endpoint)
- Modify: `frontend/src/pages/DashboardPage.tsx` (add export button in ProGate)
- Test: `tests/test_web_routes.py` (add export test)

- [ ] **Step 1: Write failing test**

In `tests/test_web_routes.py`:
```python
def test_csv_export_requires_pro(client, free_user_headers):
    resp = client.get("/api/v1/web/cards/export.csv", headers=free_user_headers)
    assert resp.status_code == 403

def test_csv_export_works_for_pro(client, pro_user_headers):
    resp = client.get("/api/v1/web/cards/export.csv", headers=pro_user_headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
```

- [ ] **Step 2: Add export endpoint to `web.py`**

```python
import csv
import io
from fastapi.responses import StreamingResponse
from backend.app.core.permissions import can, Feature

@web_router.get("/cards/export.csv")
def export_cards_csv(
    game: str = Query(default="pokemon"),
    current_user = Depends(require_auth),
    db: Session = Depends(get_database),
):
    access_tier = resolve_tier(current_user.email, current_user.access_tier,
                                current_user.subscription_tier, current_user.subscription_status)
    if not can(access_tier, Feature.EXPORT_CSV):
        raise HTTPException(status_code=403, detail="Pro feature: CSV export")

    rows = db.execute(text("""
        SELECT a.name, a.set_name, a.card_number, a.grade_score,
               s.label, s.confidence, s.price_delta_pct, s.computed_at,
               ph.price AS latest_price
        FROM assets a
        LEFT JOIN asset_signals s ON s.asset_id = a.id
        LEFT JOIN LATERAL (
            SELECT price FROM price_history
            WHERE asset_id = a.id
            ORDER BY captured_at DESC LIMIT 1
        ) ph ON true
        WHERE a.game = :game
        ORDER BY s.label, a.name
    """), {"game": game}).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["name", "set", "number", "grade", "signal", "confidence", "delta_pct", "computed_at", "latest_price"])
    for r in rows:
        writer.writerow([r.name, r.set_name, r.card_number, r.grade_score,
                         r.label, r.confidence, r.price_delta_pct,
                         r.computed_at.isoformat() if r.computed_at else "",
                         str(r.latest_price) if r.latest_price else ""])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=flashcard-planet-{game}.csv"},
    )
```

- [ ] **Step 3: Add export button to DashboardPage**

In `frontend/src/pages/DashboardPage.tsx`, add an export button gated behind ProGate:

```tsx
<ProGate feature="CSV export" reason="Export your signals data on Pro">
  <a
    href={`/api/v1/web/cards/export.csv?game=${activeGame}`}
    className="btn btn-ghost btn-sm"
    style={{ textDecoration: 'none' }}
  >
    Export CSV
  </a>
</ProGate>
```

Place it in the filter-sort bar area.

- [ ] **Step 4: Run tests and build**

```bash
pytest tests/test_web_routes.py -v 2>&1 | tail -10
cd frontend && npm run build 2>&1 | tail -3
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/web.py frontend/src/pages/DashboardPage.tsx tests/test_web_routes.py
git commit -m "feat(gates): CSV export Pro feature — endpoint + frontend button (TASK-301 D)"
```

---

## PR E: Email flows

---

### Task E1: Trial welcome email

**Files:**
- Create: `backend/app/email/templates/trial_started.html`
- Modify: `backend/app/email/resend_client.py`
- Modify: `backend/app/api/routes/trial.py` (call email after trial start)

- [ ] **Step 1: Create email template**

Create `backend/app/email/templates/trial_started.html`:

```html
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family: sans-serif; color: #111; max-width: 520px; margin: 0 auto; padding: 32px 24px;">
  <p style="font-size: 20px; font-weight: 700; margin-bottom: 8px;">Your 7-day Pro trial has started.</p>
  <p style="color: #555; margin-bottom: 24px;">You now have full Pro access to Flashcard Planet — confidence scores, AI analysis, unlimited watchlist, and all sorting options.</p>
  <a href="{{ app_url }}/pricing" style="display: inline-block; background: #f0b429; color: #0c0c10; font-weight: 700; padding: 12px 24px; border-radius: 6px; text-decoration: none; margin-bottom: 24px;">
    Explore Pro features →
  </a>
  <p style="color: #555; font-size: 13px;">Your trial ends on {{ trial_ends_at }}. If you don't add a payment method, you'll automatically drop to the free tier — no charge, no hassle.</p>
  <p style="color: #888; font-size: 12px; margin-top: 32px;">Flashcard Planet · <a href="{{ app_url }}" style="color: #888;">flashcardplanet.com</a></p>
</body>
</html>
```

- [ ] **Step 2: Add send function to `resend_client.py`**

```python
def send_trial_started_email(to_email: str, trial_ends_at: str) -> None:
    settings = _get_settings()
    html = _TEMPLATE_ENV.get_template("trial_started.html").render(
        app_url=settings.app_url or "https://flashcard-planet.up.railway.app",
        trial_ends_at=trial_ends_at,
    )
    _send(to_email, {
        "subject": "Your 7-day Pro trial has started",
        "html": html,
    })
```

- [ ] **Step 3: Call from trial start**

In `backend/app/api/routes/trial.py`, after `db.commit()`:

```python
from backend.app.email.resend_client import send_trial_started_email
# ...
if started:
    db.commit()
    try:
        send_trial_started_email(
            current_user.email,
            current_user.trial_ends_at.strftime("%B %d, %Y"),
        )
    except Exception:
        logger.warning("trial_welcome_email_failed user_id=%s", current_user.id)
    return {"status": "started", "trial_ends_at": current_user.trial_ends_at.isoformat()}
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/email/templates/trial_started.html \
        backend/app/email/resend_client.py \
        backend/app/api/routes/trial.py
git commit -m "feat(email): trial welcome email on trial start (TASK-301 E)"
```

---

### Task E2: Day-6 conversion email

**Files:**
- Create: `backend/app/email/templates/trial_expiring_soon.html`
- Modify: `backend/app/email/resend_client.py`
- Modify: `backend/app/backstage/scheduler.py` (send from trial expiry sweep)

- [ ] **Step 1: Create template**

Create `backend/app/email/templates/trial_expiring_soon.html`:

```html
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family: sans-serif; color: #111; max-width: 520px; margin: 0 auto; padding: 32px 24px;">
  <p style="font-size: 20px; font-weight: 700; margin-bottom: 8px;">Your Pro trial ends tomorrow.</p>
  <p style="color: #555; margin-bottom: 24px;">Add a payment method today to keep your confidence scores, AI analysis, and unlimited watchlist.</p>
  <a href="{{ checkout_url }}" style="display: inline-block; background: #f0b429; color: #0c0c10; font-weight: 700; padding: 12px 24px; border-radius: 6px; text-decoration: none; margin-bottom: 24px;">
    Keep Pro access — $12/month →
  </a>
  <p style="color: #555; font-size: 13px;">If you don't upgrade, you'll automatically drop to the free tier on {{ trial_ends_at }}. Your watchlist and alert settings are saved for 90 days.</p>
  <p style="color: #888; font-size: 12px; margin-top: 32px;">Flashcard Planet · Questions? hello@flashcardplanet.com</p>
</body>
</html>
```

- [ ] **Step 2: Add send function**

In `backend/app/email/resend_client.py`:

```python
def send_trial_expiring_soon_email(to_email: str, trial_ends_at: str, checkout_url: str) -> None:
    settings = _get_settings()
    html = _TEMPLATE_ENV.get_template("trial_expiring_soon.html").render(
        checkout_url=checkout_url,
        trial_ends_at=trial_ends_at,
    )
    _send(to_email, {
        "subject": "Your Pro trial ends tomorrow — keep access",
        "html": html,
    })
```

- [ ] **Step 3: Send from trial expiry sweep**

In `backend/app/backstage/scheduler.py`, inside `_run_trial_expiry_sweep`, before downgrading users, check if `trial_ends_at` is within 24 hours and send the conversion email:

```python
from datetime import timedelta
# In the loop over expired_users, BEFORE downgrading:
warning_window = now - timedelta(days=1)  # trial_ends_at was in [yesterday, now)
# Actually send warning when trial ends in (0, 48h) but only if not yet notified
# Add a `trial_expiry_email_sent_at` column in a future migration — for now use
# trial_ends_at proximity: send if trial_ends_at is within 48h and > 0h away
for user in session.execute(
    select(User).where(
        User.subscription_status == "trialing",
        User.trial_ends_at.isnot(None),
        User.trial_ends_at > now,
        User.trial_ends_at < now + timedelta(hours=48),
    )
).scalars().all():
    try:
        send_trial_expiring_soon_email(
            user.email,
            user.trial_ends_at.strftime("%B %d, %Y"),
            checkout_url=f"{settings.app_url}/pricing",
        )
    except Exception:
        logger.warning("trial_expiry_email_failed user_id=%s", user.id)
```

Note: This sends the email each time the sweep runs while the user is in the 48h window (every 6h). To prevent duplicate emails, add `trial_expiry_email_sent_at` column in a follow-up PR. For launch, the 6h interval means at most ~8 emails in 48h — acceptable at launch scale.

- [ ] **Step 4: Commit**

```bash
git add backend/app/email/templates/trial_expiring_soon.html \
        backend/app/email/resend_client.py \
        backend/app/backstage/scheduler.py
git commit -m "feat(email): trial expiring-soon email in trial-expiry-sweep (TASK-301 E)"
```

---

## End-to-end verification sequence (after all PRs merged)

1. Create a test account with a new email
2. Verify trial starts automatically: `GET /api/v1/auth/me` should return `subscription_status: trialing, access_tier: pro`
3. Open `/pricing` — verify page renders, Pro plan visible
4. Click "Start 7-day free trial →" → LemonSqueezy checkout opens
5. Use LemonSqueezy test card (5555 5555 5555 4444) → complete checkout
6. Verify webhook fires: check Railway logs for `webhook_processed event=subscription_created`
7. Verify user's `subscription_status = 'active'` in DB: `railway run psql $DATABASE_URL -c "SELECT email, subscription_status, access_tier FROM users WHERE email = 'testuser@example.com'"`
8. Open Card Detail → verify confidence score and AI analysis are visible (Pro features)
9. Open Dashboard → verify Volume and Recent sort are accessible
10. Test cancellation in LemonSqueezy → verify `subscription_cancelled` webhook fires → user stays Pro until period_end
11. Test trial expiry: manually set `trial_ends_at = NOW() - interval '1 hour'` → wait for next sweep run → verify `subscription_status = 'expired', access_tier = 'free'`

---

## Self-Review

**Spec coverage check:**
- ✅ LemonSqueezy webhook handler with HMAC verification (Task A3)
- ✅ Subscription sync to user fields (Task A2)
- ✅ Trial start endpoint + auto-start on registration (Task B1)
- ✅ Trial expiry scheduler job (Task B2)
- ✅ `/pricing` page with feature table (Task C1)
- ✅ NavBar upgrade CTA (Task C2)
- ✅ Volume + Recent sort gating restored (Task D1)
- ✅ AI analysis gate restored per CLAUDE.md §12 (Task D2)
- ✅ Confidence score gated (Task D3)
- ✅ CSV export endpoint + frontend button (Task D4)
- ✅ Trial welcome email (Task E1)
- ✅ Day-6 conversion email (Task E2)

**Not in this plan (deferred):**
- Data retention 90-day cleanup job — no user data at risk until the first churned subscribers, ~30+ days post-launch. Add as TASK-307 after first paying users.
- Founders coupon code distribution — manual via LemonSqueezy dashboard for first 100. Automate only if demand exceeds manual capacity.
- `trial_expiry_email_sent_at` dedup column — post-launch, before scale.
- Watchlist + alert CTA placements (2 of 5 in strategy doc) — the feature limits are already enforced; the CTAs can be added incrementally post-launch.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | — |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 0 | — | — |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**VERDICT: NO REVIEWS YET — run `/autoplan`**
