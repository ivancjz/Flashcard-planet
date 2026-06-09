from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
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


def _verify_signature(raw_body: bytes, signature: str | None, secret: str) -> None:
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

    sub_event = SubscriptionEvent(
        event_id=event_id,
        event_name=event_name,
        subscription_provider_id=sub_id,
        payload_json=raw_body.decode("utf-8", errors="replace"),
    )

    # Find the user — custom_data.user_id first, then email
    user: User | None = None
    custom_data = meta.get("custom_data", {})
    user_id_str = custom_data.get("user_id")
    if user_id_str:
        try:
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
            event_name,
            sub_id,
            user_email,
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
        "webhook_processed event=%s sub_id=%s user_id=%s new_status=%s",
        event_name,
        sub_id,
        user.id,
        status,
    )
    return {"status": "ok"}
