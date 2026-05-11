from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest


def test_trial_sets_trialing_status():
    from backend.app.api.routes.trial import _start_trial_for_user

    user = MagicMock()
    user.subscription_status = "free"
    user.trial_ends_at = None
    user.trial_started_at = None

    now = datetime.now(timezone.utc)
    started = _start_trial_for_user(user, now=now)

    assert started is True
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

    started = _start_trial_for_user(user, now=datetime.now(timezone.utc))

    assert started is False
    assert user.subscription_status == "active"


def test_trial_does_not_restart_if_already_trialing():
    from backend.app.api.routes.trial import _start_trial_for_user

    user = MagicMock()
    user.subscription_status = "trialing"
    original_end = datetime.now(timezone.utc) + timedelta(days=5)
    user.trial_ends_at = original_end

    _start_trial_for_user(user, now=datetime.now(timezone.utc))

    # Should not reset trial_ends_at — still 5 days away
    assert (user.trial_ends_at - datetime.now(timezone.utc)).total_seconds() > 4 * 86400
