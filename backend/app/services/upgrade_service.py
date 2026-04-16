"""
Upgrade request lifecycle — no Stripe, manual-approval model.

States
------
  pending   → created by user, awaiting admin action
  approved  → admin approved; user tier promoted to "pro"
  rejected  → admin rejected; user tier unchanged
  cancelled → user withdrew the request before admin acted

DB table: upgrade_requests  (migration 0010)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.enums import AccessTier
from backend.app.models.upgrade_request import UpgradeRequest
from backend.app.models.user import User
from backend.app.services.user_service import set_user_tier


# ── Enums ────────────────────────────────────────────────────────────────────

class UpgradeRequestStatus(str, Enum):
    PENDING   = "pending"
    APPROVED  = "approved"
    REJECTED  = "rejected"
    CANCELLED = "cancelled"


# ── Result type ──────────────────────────────────────────────────────────────

@dataclass
class UpgradeRequestResult:
    ok: bool
    request_id: uuid.UUID | None = None
    status: str | None = None
    error: str | None = None


# ── Public API ───────────────────────────────────────────────────────────────

def submit_upgrade_request(
    db: Session,
    user_id: uuid.UUID,
    note: str | None = None,
) -> UpgradeRequestResult:
    """
    User submits an upgrade request.

    - Idempotent: if a pending request already exists, returns it.
    - Blocked: if user is already Pro.
    """
    user: User | None = db.get(User, user_id)
    if user is None:
        return UpgradeRequestResult(ok=False, error="User not found.")

    if user.access_tier == AccessTier.PRO:
        return UpgradeRequestResult(ok=False, error="Account is already Pro.")

    existing = db.scalars(
        select(UpgradeRequest).where(
            UpgradeRequest.user_id == user_id,
            UpgradeRequest.status == UpgradeRequestStatus.PENDING,
        )
    ).first()
    if existing:
        return UpgradeRequestResult(
            ok=True, request_id=existing.id, status=existing.status
        )

    req = UpgradeRequest(
        id=uuid.uuid4(),
        user_id=user_id,
        status=UpgradeRequestStatus.PENDING,
        note=note or "",
        created_at=datetime.now(UTC),
    )
    db.add(req)
    db.flush()

    return UpgradeRequestResult(ok=True, request_id=req.id, status=req.status)


def get_upgrade_status(db: Session, user_id: uuid.UUID) -> dict:
    """Return the most recent upgrade request state for a user."""
    user: User | None = db.get(User, user_id)

    req: UpgradeRequest | None = db.scalars(
        select(UpgradeRequest)
        .where(UpgradeRequest.user_id == user_id)
        .order_by(UpgradeRequest.created_at.desc())
    ).first()

    is_pro = user.access_tier == AccessTier.PRO if user else False

    if is_pro:
        return {"tier": "pro", "request_status": None}

    if req is None:
        return {"tier": "free", "request_status": None}

    return {
        "tier": user.access_tier if user else "free",
        "request_status": req.status,
        "request_id": str(req.id),
        "created_at": req.created_at.isoformat(),
    }


def approve_upgrade_request(
    db: Session,
    request_id: uuid.UUID,
    admin_note: str | None = None,
) -> UpgradeRequestResult:
    """Admin approves a pending request. Promotes user to Pro."""
    req: UpgradeRequest | None = db.get(UpgradeRequest, request_id)
    if req is None:
        return UpgradeRequestResult(ok=False, error="Request not found.")

    if req.status != UpgradeRequestStatus.PENDING:
        return UpgradeRequestResult(
            ok=False,
            error=f"Request is already '{req.status}', cannot approve.",
        )

    req.status = UpgradeRequestStatus.APPROVED
    req.resolved_at = datetime.now(UTC)
    req.admin_note = admin_note or ""
    db.flush()

    user: User | None = db.get(User, req.user_id)
    if user is not None:
        set_user_tier(db, user, AccessTier.PRO)

    return UpgradeRequestResult(ok=True, request_id=req.id, status=req.status)


def reject_upgrade_request(
    db: Session,
    request_id: uuid.UUID,
    admin_note: str | None = None,
) -> UpgradeRequestResult:
    """Admin rejects a pending request. User tier unchanged."""
    req: UpgradeRequest | None = db.get(UpgradeRequest, request_id)
    if req is None:
        return UpgradeRequestResult(ok=False, error="Request not found.")

    if req.status != UpgradeRequestStatus.PENDING:
        return UpgradeRequestResult(
            ok=False,
            error=f"Request is already '{req.status}', cannot reject.",
        )

    req.status = UpgradeRequestStatus.REJECTED
    req.resolved_at = datetime.now(UTC)
    req.admin_note = admin_note or ""
    db.flush()

    return UpgradeRequestResult(ok=True, request_id=req.id, status=req.status)


def cancel_upgrade_request(db: Session, user_id: uuid.UUID) -> UpgradeRequestResult:
    """User withdraws their pending request."""
    req: UpgradeRequest | None = db.scalars(
        select(UpgradeRequest).where(
            UpgradeRequest.user_id == user_id,
            UpgradeRequest.status == UpgradeRequestStatus.PENDING,
        )
    ).first()
    if req is None:
        return UpgradeRequestResult(ok=False, error="No pending request found.")

    req.status = UpgradeRequestStatus.CANCELLED
    req.resolved_at = datetime.now(UTC)
    db.flush()

    return UpgradeRequestResult(ok=True, request_id=req.id, status=req.status)


def list_pending_requests(db: Session) -> list[UpgradeRequest]:
    """Admin queue: all pending requests, oldest first."""
    return list(
        db.scalars(
            select(UpgradeRequest)
            .where(UpgradeRequest.status == UpgradeRequestStatus.PENDING)
            .order_by(UpgradeRequest.created_at.asc())
        ).all()
    )
