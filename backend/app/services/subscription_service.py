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
