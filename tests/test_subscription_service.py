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
