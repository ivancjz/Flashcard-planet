import hashlib
import hmac
import json
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.deps import get_database
from backend.app.api.routes.webhooks import router as webhooks_router
from backend.app.core.config import get_settings


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _make_payload(event_name: str, status: str, email: str = "test@example.com") -> dict:
    return {
        "meta": {
            "event_name": event_name,
            "event_id": f"evt_{event_name}_{status}",
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


def _make_app():
    app = FastAPI()
    app.include_router(webhooks_router, prefix="/api/v1")
    app.dependency_overrides[get_database] = lambda: (yield MagicMock())
    return app


def test_webhook_rejects_missing_signature():
    client = TestClient(_make_app())
    payload = json.dumps(_make_payload("subscription_created", "active")).encode()
    resp = client.post(
        "/api/v1/webhooks/lemonsqueezy",
        content=payload,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 401


def test_webhook_rejects_invalid_signature():
    client = TestClient(_make_app())
    payload = json.dumps(_make_payload("subscription_created", "active")).encode()
    resp = client.post(
        "/api/v1/webhooks/lemonsqueezy",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-Signature": "badhex000000000000000000000000000000000000000000000000000000000000",
        },
    )
    assert resp.status_code == 401
