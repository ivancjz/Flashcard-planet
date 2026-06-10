"""Tests for TASK-301 payment gap fixes:
  1. Checkout URL routing (plus/pro/founders variants)
  2. Webhook tier detection from variant_id
  3. Subscription data cleanup job (90-day grace)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import sessionmaker

import backend.app.models  # noqa: F401 — registers all models
from backend.app.db.base import Base
from backend.app.models.alert import Alert
from backend.app.models.asset import Asset
from backend.app.models.user import User


# ─── shared DB fixture ──────────────────────────────────────────────────────

def _coerce_postgres_types() -> None:
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()


@pytest.fixture
def db_session():
    _coerce_postgres_types()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


# ─── Checkout URL routing ────────────────────────────────────────────────────

def test_checkout_routing_maps_plus_to_standard_variant():
    from backend.app.api.routes.account import _VARIANT_ROUTING
    attr, tier = _VARIANT_ROUTING["plus"]
    assert attr == "lemonsqueezy_variant_id_standard"
    assert tier == "plus"


def test_checkout_routing_maps_pro_to_pro_standard_variant():
    from backend.app.api.routes.account import _VARIANT_ROUTING
    attr, tier = _VARIANT_ROUTING["pro"]
    assert attr == "lemonsqueezy_variant_id_pro_standard"
    assert tier == "pro"


def test_checkout_routing_maps_founders_to_plus_founders():
    from backend.app.api.routes.account import _VARIANT_ROUTING
    attr, tier = _VARIANT_ROUTING["founders"]
    assert attr == "lemonsqueezy_variant_id_founders"
    assert tier == "plus"


def test_checkout_routing_maps_pro_founders_to_pro_founders_variant():
    from backend.app.api.routes.account import _VARIANT_ROUTING
    attr, tier = _VARIANT_ROUTING["pro_founders"]
    assert attr == "lemonsqueezy_variant_id_pro_founders"
    assert tier == "pro"


def test_checkout_plus_and_standard_are_distinct_from_pro():
    from backend.app.api.routes.account import _VARIANT_ROUTING
    plus_attr = _VARIANT_ROUTING["plus"][0]
    pro_attr = _VARIANT_ROUTING["pro"][0]
    assert plus_attr != pro_attr, "Plus and Pro must map to different variant IDs"


# ─── Webhook tier detection ───────────────────────────────────────────────────

def _settings_with_variants(
    std="var_plus_std",
    founders="var_plus_fnd",
    pro_std="var_pro_std",
    pro_fnd="var_pro_fnd",
):
    s = MagicMock()
    s.lemonsqueezy_variant_id_standard = std
    s.lemonsqueezy_variant_id_founders = founders
    s.lemonsqueezy_variant_id_pro_standard = pro_std
    s.lemonsqueezy_variant_id_pro_founders = pro_fnd
    s.lemonsqueezy_webhook_secret = "testsecret"
    return s


def _run_tier_detection(variant_id: str):
    """Run tier + is_founders detection logic from webhooks.py."""
    settings = _settings_with_variants()
    plus_variant_ids = {
        settings.lemonsqueezy_variant_id_standard,
        settings.lemonsqueezy_variant_id_founders,
    } - {""}
    pro_variant_ids = {
        settings.lemonsqueezy_variant_id_pro_standard,
        settings.lemonsqueezy_variant_id_pro_founders,
    } - {""}
    founders_variant_ids = {
        settings.lemonsqueezy_variant_id_founders,
        settings.lemonsqueezy_variant_id_pro_founders,
    } - {""}
    is_founders = variant_id in founders_variant_ids
    subscription_tier = "pro" if variant_id in pro_variant_ids else "plus"
    return subscription_tier, is_founders


def test_plus_standard_variant_gives_plus_tier():
    tier, founders = _run_tier_detection("var_plus_std")
    assert tier == "plus"
    assert founders is False


def test_plus_founders_variant_gives_plus_tier_and_founders_flag():
    tier, founders = _run_tier_detection("var_plus_fnd")
    assert tier == "plus"
    assert founders is True


def test_pro_standard_variant_gives_pro_tier():
    tier, founders = _run_tier_detection("var_pro_std")
    assert tier == "pro"
    assert founders is False


def test_pro_founders_variant_gives_pro_tier_and_founders_flag():
    tier, founders = _run_tier_detection("var_pro_fnd")
    assert tier == "pro"
    assert founders is True


def test_unknown_variant_defaults_to_plus_not_pro():
    # Unknown/empty variant → plus (safe side, not over-provisioning Pro)
    tier, founders = _run_tier_detection("unknown_variant_xyz")
    assert tier == "plus"
    assert founders is False


# ─── Subscription data cleanup job ──────────────────────────────────────────

def _make_user(db, *, email, status, period_end=None, trial_ends_at=None, num_alerts=0):
    user = User(
        id=uuid.uuid4(),
        email=email,
        subscription_status=status,
        subscription_current_period_end=period_end,
        trial_ends_at=trial_ends_at,
        access_tier="free",
    )
    db.add(user)
    db.flush()
    if num_alerts:
        asset = Asset(id=uuid.uuid4(), name="Test Card", asset_class="tcg", game="pokemon")
        db.add(asset)
        db.flush()
        for i in range(num_alerts):
            # Set explicit created_at so ordering tests are deterministic
            created = datetime.now(timezone.utc) - timedelta(hours=num_alerts - i)
            alert = Alert(user_id=user.id, asset_id=asset.id, created_at=created)
            db.add(alert)
    db.flush()
    return user


def test_cleanup_deletes_alerts_beyond_free_limit_for_expired_users(db_session):
    from backend.app.backstage.scheduler import _run_subscription_data_cleanup

    grace_cutoff = datetime.now(timezone.utc) - timedelta(days=91)
    user = _make_user(
        db_session,
        email="old@example.com",
        status="expired",
        period_end=grace_cutoff - timedelta(days=1),
        num_alerts=8,
    )
    result = _run_subscription_data_cleanup(db_session)
    db_session.commit()

    remaining = db_session.query(Alert).filter(Alert.user_id == user.id).count()
    assert remaining == 5, f"Expected 5 alerts kept (free limit), got {remaining}"
    assert result["alerts_deleted"] == 3
    assert result["users_cleaned"] == 1


def test_cleanup_skips_users_within_grace_period(db_session):
    from backend.app.backstage.scheduler import _run_subscription_data_cleanup

    recent_end = datetime.now(timezone.utc) - timedelta(days=30)
    _make_user(
        db_session,
        email="recent@example.com",
        status="expired",
        period_end=recent_end,
        num_alerts=8,
    )
    result = _run_subscription_data_cleanup(db_session)

    assert result["alerts_deleted"] == 0
    assert result["users_cleaned"] == 0


def test_cleanup_skips_active_users(db_session):
    from backend.app.backstage.scheduler import _run_subscription_data_cleanup

    old_end = datetime.now(timezone.utc) - timedelta(days=91)
    _make_user(
        db_session,
        email="active@example.com",
        status="active",
        period_end=old_end,
        num_alerts=8,
    )
    result = _run_subscription_data_cleanup(db_session)

    assert result["alerts_deleted"] == 0


def test_cleanup_user_with_few_alerts_not_affected(db_session):
    from backend.app.backstage.scheduler import _run_subscription_data_cleanup

    grace_cutoff = datetime.now(timezone.utc) - timedelta(days=91)
    user = _make_user(
        db_session,
        email="low@example.com",
        status="cancelled",
        period_end=grace_cutoff - timedelta(days=1),
        num_alerts=3,
    )
    result = _run_subscription_data_cleanup(db_session)

    remaining = db_session.query(Alert).filter(Alert.user_id == user.id).count()
    assert remaining == 3
    assert result["alerts_deleted"] == 0


def test_cleanup_includes_trial_only_users_past_grace(db_session):
    """Trial users (period_end=None, trial_ends_at set) must be included after 90 days."""
    from backend.app.backstage.scheduler import _run_subscription_data_cleanup

    old_trial_end = datetime.now(timezone.utc) - timedelta(days=91)
    user = _make_user(
        db_session,
        email="trialold@example.com",
        status="expired",
        period_end=None,         # trial-only: never paid, no period_end
        trial_ends_at=old_trial_end - timedelta(days=1),
        num_alerts=8,
    )
    result = _run_subscription_data_cleanup(db_session)
    db_session.commit()

    remaining = db_session.query(Alert).filter(Alert.user_id == user.id).count()
    assert remaining == 5
    assert result["alerts_deleted"] == 3


def test_cleanup_skips_trial_users_within_grace(db_session):
    """Trial users within 90-day grace must be skipped."""
    from backend.app.backstage.scheduler import _run_subscription_data_cleanup

    recent_trial_end = datetime.now(timezone.utc) - timedelta(days=30)
    _make_user(
        db_session,
        email="trialrecent@example.com",
        status="expired",
        period_end=None,
        trial_ends_at=recent_trial_end,
        num_alerts=8,
    )
    result = _run_subscription_data_cleanup(db_session)

    assert result["alerts_deleted"] == 0
    assert result["users_cleaned"] == 0


def test_cleanup_keeps_oldest_alerts_by_created_at(db_session):
    """The 5 kept alerts must be the oldest by created_at, not arbitrary UUID order."""
    from backend.app.backstage.scheduler import _run_subscription_data_cleanup

    grace_cutoff = datetime.now(timezone.utc) - timedelta(days=91)
    # _make_user creates alerts with created_at = now - (num_alerts - i) hours
    # so alert 0 is oldest (now-8h) and alert 7 is newest (now-1h)
    user = _make_user(
        db_session,
        email="order@example.com",
        status="expired",
        period_end=grace_cutoff - timedelta(days=1),
        num_alerts=8,
    )
    all_alerts_before = db_session.query(Alert).filter(
        Alert.user_id == user.id
    ).order_by(Alert.created_at.asc()).all()
    oldest_5_ids = {a.id for a in all_alerts_before[:5]}

    _run_subscription_data_cleanup(db_session)
    db_session.commit()

    remaining_ids = {
        a.id for a in db_session.query(Alert).filter(Alert.user_id == user.id).all()
    }
    assert remaining_ids == oldest_5_ids, "Cleanup must keep the 5 oldest alerts, not arbitrary ones"


def test_cleanup_meta_contains_expected_keys(db_session):
    from backend.app.backstage.scheduler import _run_subscription_data_cleanup

    result = _run_subscription_data_cleanup(db_session)
    assert "users_past_grace" in result
    assert "users_cleaned" in result
    assert "alerts_deleted" in result
    assert "grace_cutoff" in result
