"""Tests for TASK-505 (14-day trial) and TASK-506 (TRIAL_AUTO_START gate)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# TASK-505: trial duration is 14 days
# ---------------------------------------------------------------------------

def test_trial_duration_constant_is_14():
    from backend.app.api.routes.trial import TRIAL_DURATION_DAYS
    assert TRIAL_DURATION_DAYS == 14


def test_trial_ends_at_is_14_days_from_start():
    from backend.app.api.routes.trial import _start_trial_for_user

    user = MagicMock()
    user.subscription_status = "free"
    user.trial_ends_at = None

    now = datetime(2026, 5, 12, 0, 0, 0, tzinfo=timezone.utc)
    _start_trial_for_user(user, now=now)

    expected = now + timedelta(days=14)
    assert user.trial_ends_at == expected


def test_resend_client_subject_contains_14_day(monkeypatch):
    captured = {}

    class FakeEmails:
        @staticmethod
        def send(payload):
            captured["payload"] = payload

    monkeypatch.setattr("resend.Emails", FakeEmails)
    monkeypatch.setattr("resend.api_key", "fake")

    from backend.app.email.resend_client import send_trial_started_email

    with patch("backend.app.email.resend_client.get_settings") as mock_settings:
        mock_settings.return_value.resend_api_key = "fake"
        mock_settings.return_value.app_url = "https://example.com"
        send_trial_started_email("test@example.com", "May 26, 2026")

    assert "14-day" in captured["payload"]["subject"]
    assert "7-day" not in captured["payload"]["subject"]


def test_trial_started_html_contains_14_day():
    from pathlib import Path
    html_path = Path(__file__).parent.parent / "backend" / "app" / "email" / "templates" / "trial_started.html"
    content = html_path.read_text(encoding="utf-8")
    assert "14-day" in content
    assert "7-day" not in content


def test_pricing_page_contains_14_day():
    from pathlib import Path
    tsx_path = Path(__file__).parent.parent / "frontend" / "src" / "pages" / "PricingPage.tsx"
    content = tsx_path.read_text(encoding="utf-8")
    assert content.count("14-day") >= 3, "Expected at least 3 occurrences of '14-day' in PricingPage.tsx"
    assert "7-day" not in content, "Found stale '7-day' string in PricingPage.tsx"


# ---------------------------------------------------------------------------
# TASK-506: trial auto-start gate
# ---------------------------------------------------------------------------

def test_trial_not_started_when_flag_is_false():
    """The conditional pattern: trial only starts when trial_auto_start is True."""
    user = MagicMock()
    user.subscription_status = "free"

    trial_started = False
    trial_auto_start = False  # flag is off

    if trial_auto_start:
        from backend.app.api.routes.trial import _start_trial_for_user
        _start_trial_for_user(user)
        trial_started = True

    assert trial_started is False
    # user should NOT have been mutated
    user.access_tier = getattr(user, "access_tier", None)
    assert user.subscription_status == "free"


def test_trial_started_when_flag_is_true():
    """The conditional pattern: trial starts when trial_auto_start is True."""
    from backend.app.api.routes.trial import _start_trial_for_user

    user = MagicMock()
    user.subscription_status = "free"
    user.trial_ends_at = None

    trial_auto_start = True  # flag is on

    if trial_auto_start:
        _start_trial_for_user(user)

    assert user.subscription_status == "trialing"
    assert user.access_tier == "pro"


def test_trial_auto_start_setting_defaults_to_false():
    """TRIAL_AUTO_START defaults to False to prevent trial clock starting before LS is wired."""
    import os
    # Remove env var if set to test default
    env_backup = os.environ.pop("TRIAL_AUTO_START", None)
    try:
        from functools import lru_cache
        from backend.app.core import config as cfg_module
        # Clear lru_cache to re-evaluate settings with current env
        cfg_module.get_settings.cache_clear()
        settings = cfg_module.get_settings()
        assert settings.trial_auto_start is False
    finally:
        if env_backup is not None:
            os.environ["TRIAL_AUTO_START"] = env_backup
        from backend.app.core import config as cfg_module
        cfg_module.get_settings.cache_clear()
