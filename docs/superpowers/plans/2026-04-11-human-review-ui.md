# Human Review UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an operator-facing `/backstage/review` page and REST endpoints for resolving low-confidence ingestion matches via Accept, Override, or Dismiss.

**Architecture:** Five JSON endpoints under `/api/v1/admin/review/` protected by `X-Admin-Key`, backed by a new `review_routes.py` service file. The browser page is a server-rendered HTML shell; JS handles the key prompt, queue loading, modal, and resolution calls. Each resolution action runs in a single DB transaction with full downstream writes (price event + mapping cache) for Accept/Override, and status-only writes for Dismiss.

**Tech Stack:** Python, FastAPI, SQLAlchemy 2.x, PostgreSQL, Alembic, vanilla JS (no framework), inline HTML in `site.py`.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/app/models/human_review.py` | Modify | Add `resolution_type` column |
| `alembic/versions/0008_add_review_resolution_type.py` | Create | DB migration |
| `backend/app/backstage/review_routes.py` | Create | All 5 API endpoints + resolution logic |
| `backend/app/api/router.py` | Modify | Register review router under `api_prefix` |
| `backend/app/site.py` | Modify | `GET /backstage/review` HTML shell |
| `backend/app/static/site.css` | Modify | Review page styles |
| `tests/test_human_review_api.py` | Create | Import + callable + model field tests |

---

## Task 1: Add `resolution_type` to `HumanReviewQueue` + migration

**Files:**
- Modify: `backend/app/models/human_review.py`
- Create: `alembic/versions/0008_add_review_resolution_type.py`
- Test: `tests/test_human_review_api.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_human_review_api.py`:

```python
"""Tests for human review API endpoints and model."""
from __future__ import annotations

from backend.app.models.human_review import HumanReviewQueue


def test_human_review_queue_has_resolution_type():
    """HumanReviewQueue must have resolution_type field defaulting to None."""
    row = HumanReviewQueue(
        raw_listing_id=__import__("uuid").uuid4(),
        raw_title="Charizard VMAX PSA 10",
    )
    assert hasattr(row, "resolution_type")
    assert row.resolution_type is None
```

- [ ] **Step 2: Run test to verify it fails**

```
cd c:/Flashcard-planet
python -m pytest tests/test_human_review_api.py::test_human_review_queue_has_resolution_type -v
```

Expected: `FAILED` — `AssertionError` or `AttributeError`.

- [ ] **Step 3: Add `resolution_type` to the model**

In `backend/app/models/human_review.py`, add the import for `nullable` (already imported via `String`) and add the column after `resolved_by`:

```python
    resolution_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
```

Full updated file (replace entirely):

```python
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from backend.app.db.base import Base


class HumanReviewQueue(Base):
    __tablename__ = "human_review_queue"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    raw_listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_listings.id"), nullable=False
    )
    raw_title: Mapped[str] = mapped_column(Text, nullable=False)
    best_guess_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("assets.id"))
    best_guess_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    reason: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(100))
    resolution_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
```

- [ ] **Step 4: Run test to verify it passes**

```
python -m pytest tests/test_human_review_api.py::test_human_review_queue_has_resolution_type -v
```

Expected: `PASSED`.

- [ ] **Step 5: Write the migration**

Create `alembic/versions/0008_add_review_resolution_type.py`:

```python
"""Add resolution_type to human_review_queue.

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-11 00:00:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "human_review_queue",
        sa.Column("resolution_type", sa.String(16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("human_review_queue", "resolution_type")
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/human_review.py alembic/versions/0008_add_review_resolution_type.py tests/test_human_review_api.py
git commit -m "feat: add resolution_type to HumanReviewQueue + migration 0008"
```

---

## Task 2: Review API — list and asset search endpoints

**Files:**
- Create: `backend/app/backstage/review_routes.py`
- Modify: `backend/app/api/router.py`
- Test: `tests/test_human_review_api.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_human_review_api.py`:

```python
def test_review_routes_importable():
    from backend.app.backstage.review_routes import router
    assert router is not None


def test_review_routes_has_list_endpoint():
    from backend.app.backstage.review_routes import router
    paths = [r.path for r in router.routes]
    assert "/" in paths or "" in paths


def test_review_routes_has_asset_search():
    from backend.app.backstage.review_routes import router
    paths = [r.path for r in router.routes]
    assert "/assets/search" in paths
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/test_human_review_api.py::test_review_routes_importable -v
```

Expected: `FAILED` — `ModuleNotFoundError`.

- [ ] **Step 3: Create `backend/app/backstage/review_routes.py`**

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.backstage.routes import require_admin_key
from backend.app.ingestion.matcher import mapping_cache
from backend.app.ingestion.matcher.rule_engine import normalize_listing_title
from backend.app.models.asset import Asset
from backend.app.models.human_review import HumanReviewQueue
from backend.app.models.price_history import PriceHistory
from backend.app.models.raw_listing import RawListing, RawListingStatus

router = APIRouter(prefix="/admin/review", tags=["admin-review"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class ReviewItem(BaseModel):
    id: uuid.UUID
    raw_title: str
    best_guess_asset_id: uuid.UUID | None
    best_guess_asset_name: str | None
    best_guess_confidence: Decimal | None
    reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewListResponse(BaseModel):
    items: list[ReviewItem]
    total_pending: int
    limit: int
    offset: int


class AssetResult(BaseModel):
    id: uuid.UUID
    name: str
    set_name: str | None
    variant: str | None

    model_config = {"from_attributes": True}


class OverrideRequest(BaseModel):
    asset_id: uuid.UUID


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_unresolved(db: Session, review_id: uuid.UUID) -> HumanReviewQueue:
    row = db.get(HumanReviewQueue, review_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Review item not found.")
    if row.resolved_at is not None:
        raise HTTPException(status_code=409, detail="Review item already resolved.")
    return row


def _load_pending_listing(db: Session, raw_listing_id: uuid.UUID) -> RawListing:
    listing = db.get(RawListing, raw_listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Linked raw listing not found.")
    if listing.status != RawListingStatus.PENDING.value:
        raise HTTPException(
            status_code=409,
            detail="Listing already processed by another workflow.",
        )
    return listing


def _write_price_event(db: Session, asset_id: uuid.UUID, listing: RawListing) -> None:
    if listing.price_usd is None or listing.sold_at is None:
        raise HTTPException(status_code=422, detail="Listing missing required price data.")
    db.add(PriceHistory(
        asset_id=asset_id,
        source="ebay",
        currency="USD",
        price=listing.price_usd,
        captured_at=listing.sold_at,
    ))


def _stamp_resolved(row: HumanReviewQueue, resolution_type: str) -> None:
    row.resolved_at = datetime.now(UTC)
    row.resolved_by = "operator"
    row.resolution_type = resolution_type


def _mark_listing_processed(
    db: Session, listing: RawListing, asset_id: uuid.UUID, method: str
) -> None:
    db.execute(
        update(RawListing)
        .where(RawListing.id == listing.id)
        .values(
            status=RawListingStatus.PROCESSED.value,
            mapped_asset_id=asset_id,
            match_method=method,
            processed_at=datetime.now(UTC),
        )
    )


def _mark_listing_failed(db: Session, listing: RawListing) -> None:
    db.execute(
        update(RawListing)
        .where(RawListing.id == listing.id)
        .values(
            status=RawListingStatus.FAILED.value,
            error_reason="review_dismissed",
            processed_at=datetime.now(UTC),
        )
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=ReviewListResponse)
def list_review_items(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> ReviewListResponse:
    base_q = select(HumanReviewQueue).where(HumanReviewQueue.resolved_at.is_(None))

    total_pending = db.scalar(
        select(__import__("sqlalchemy").func.count()).select_from(
            base_q.subquery()
        )
    ) or 0

    rows = db.scalars(
        base_q.order_by(HumanReviewQueue.created_at.desc()).limit(limit).offset(offset)
    ).all()

    asset_ids = [r.best_guess_asset_id for r in rows if r.best_guess_asset_id]
    asset_names: dict[uuid.UUID, str] = {}
    if asset_ids:
        for asset in db.scalars(select(Asset).where(Asset.id.in_(asset_ids))).all():
            asset_names[asset.id] = asset.name

    items = [
        ReviewItem(
            id=r.id,
            raw_title=r.raw_title,
            best_guess_asset_id=r.best_guess_asset_id,
            best_guess_asset_name=asset_names.get(r.best_guess_asset_id) if r.best_guess_asset_id else None,
            best_guess_confidence=r.best_guess_confidence,
            reason=r.reason,
            created_at=r.created_at,
        )
        for r in rows
    ]

    return ReviewListResponse(
        items=items,
        total_pending=total_pending,
        limit=limit,
        offset=offset,
    )


@router.get("/assets/search", response_model=list[AssetResult])
def search_assets(
    q: str = Query(..., min_length=3),
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> list[AssetResult]:
    rows = db.scalars(
        select(Asset)
        .where(Asset.name.ilike(f"%{q}%"))
        .order_by(Asset.name.asc())
        .limit(20)
    ).all()
    return [AssetResult(id=r.id, name=r.name, set_name=r.set_name, variant=r.variant) for r in rows]


@router.post("/{review_id}/accept", status_code=200)
def accept_review(
    review_id: uuid.UUID,
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> dict:
    row = _load_unresolved(db, review_id)
    if row.best_guess_asset_id is None:
        raise HTTPException(status_code=422, detail="No best guess to accept.")
    listing = _load_pending_listing(db, row.raw_listing_id)
    _write_price_event(db, row.best_guess_asset_id, listing)
    _mark_listing_processed(db, listing, row.best_guess_asset_id, "human_review_accept")
    mapping_cache.write(
        db,
        normalized_title=normalize_listing_title(listing.raw_title),
        asset_id=row.best_guess_asset_id,
        confidence=row.best_guess_confidence or Decimal("1.0"),
        method="human_review",
    )
    _stamp_resolved(row, "accepted")
    db.commit()
    return {"status": "accepted", "review_id": str(review_id)}


@router.post("/{review_id}/override", status_code=200)
def override_review(
    review_id: uuid.UUID,
    body: OverrideRequest,
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> dict:
    row = _load_unresolved(db, review_id)
    asset = db.get(Asset, body.asset_id)
    if asset is None:
        raise HTTPException(status_code=422, detail="Asset not found.")
    listing = _load_pending_listing(db, row.raw_listing_id)
    _write_price_event(db, body.asset_id, listing)
    _mark_listing_processed(db, listing, body.asset_id, "human_review_override")
    mapping_cache.write(
        db,
        normalized_title=normalize_listing_title(listing.raw_title),
        asset_id=body.asset_id,
        confidence=Decimal("1.0"),
        method="human_review",
    )
    _stamp_resolved(row, "overridden")
    db.commit()
    return {"status": "overridden", "review_id": str(review_id), "asset_id": str(body.asset_id)}


@router.post("/{review_id}/dismiss", status_code=200)
def dismiss_review(
    review_id: uuid.UUID,
    _: None = Depends(require_admin_key),
    db: Session = Depends(get_database),
) -> dict:
    row = _load_unresolved(db, review_id)
    listing = _load_pending_listing(db, row.raw_listing_id)
    _mark_listing_failed(db, listing)
    _stamp_resolved(row, "dismissed")
    db.commit()
    return {"status": "dismissed", "review_id": str(review_id)}
```

- [ ] **Step 4: Register the router in `backend/app/api/router.py`**

Add after the existing imports and `include_router` calls:

```python
from backend.app.backstage.review_routes import router as review_router
```

And add at the end of the router registrations:

```python
api_router.include_router(review_router, prefix=settings.api_prefix)
```

The final `router.py` should look like:

```python
from fastapi import APIRouter

from backend.app.backstage.routes import router as backstage_router
from backend.app.backstage.review_routes import router as review_router
from backend.app.api.routes.alerts import router as alerts_router
from backend.app.api.routes.auth import api_router as auth_api_router
from backend.app.api.routes.auth import web_router as auth_web_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.prices import router as prices_router
from backend.app.api.routes.signals import router as signals_router
from backend.app.api.routes.watchlists import router as watchlists_router
from backend.app.core.config import get_settings

settings = get_settings()

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(backstage_router)
api_router.include_router(auth_web_router)
api_router.include_router(auth_api_router, prefix=settings.api_prefix)
api_router.include_router(alerts_router, prefix=settings.api_prefix)
api_router.include_router(prices_router, prefix=settings.api_prefix)
api_router.include_router(signals_router, prefix=settings.api_prefix)
api_router.include_router(watchlists_router, prefix=settings.api_prefix)
api_router.include_router(review_router, prefix=settings.api_prefix)
```

- [ ] **Step 5: Run tests to verify they pass**

```
python -m pytest tests/test_human_review_api.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 6: Verify app imports cleanly**

```
python -c "from backend.app.main import app; print('OK')"
```

Expected: `OK`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/backstage/review_routes.py backend/app/api/router.py tests/test_human_review_api.py
git commit -m "feat: add human review API endpoints (list, search, accept, override, dismiss)"
```

---

## Task 3: `/backstage/review` HTML page

**Files:**
- Modify: `backend/app/site.py`
- Test: `tests/test_human_review_api.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_human_review_api.py`:

```python
def test_backstage_review_route_exists():
    from backend.app.site import router
    paths = [r.path for r in router.routes]
    assert "/backstage/review" in paths
```

- [ ] **Step 2: Run test to verify it fails**

```
python -m pytest tests/test_human_review_api.py::test_backstage_review_route_exists -v
```

Expected: `FAILED`.

- [ ] **Step 3: Add the route to `backend/app/site.py`**

Add the following route near the end of `site.py`, before the `/dashboard/snapshot` route. The route renders a pure HTML shell; all data is fetched by JS.

```python
@router.get("/backstage/review", response_class=HTMLResponse)
def backstage_review_page(request: Request) -> HTMLResponse:
    username = _session_username(request)
    api_base = f"{settings.api_prefix}/admin/review"
    body = f"""
    <section class="page-intro">
      <div>
        <p class="eyebrow">Backstage · Operator</p>
        <h1>Human Review Queue</h1>
        <p class="lede">Review and resolve low-confidence ingestion matches. Requires admin key.</p>
      </div>
    </section>

    <section class="review-page" id="review-page">

      <div class="review-key-prompt" id="review-key-prompt">
        <div class="review-key-card">
          <h2>Enter admin key</h2>
          <p>Your key is stored in <code>sessionStorage</code> for this tab only.</p>
          <form id="key-form" class="review-key-form">
            <input id="admin-key-input" type="password" placeholder="Admin key" autocomplete="off" />
            <button class="button button-primary" type="submit">Unlock</button>
          </form>
          <p class="review-error" id="key-error"></p>
        </div>
      </div>

      <div class="review-queue-view" id="review-queue-view" style="display:none">
        <div class="review-queue-header">
          <h2 id="queue-heading">Pending reviews</h2>
          <button class="button button-secondary" id="refresh-btn" type="button">Refresh</button>
        </div>
        <div id="queue-list"></div>
      </div>

      <div class="review-modal-backdrop" id="modal-backdrop" style="display:none">
        <div class="review-modal" id="review-modal">
          <button class="review-modal-close" id="modal-close" type="button">✕</button>
          <p class="review-modal-label">Raw title</p>
          <p class="review-modal-title" id="modal-raw-title"></p>
          <div class="review-modal-meta" id="modal-meta"></div>
          <div class="review-modal-actions" id="modal-actions"></div>
          <div class="review-override-search" id="override-search" style="display:none">
            <input id="override-input" type="search" placeholder="Search assets (min 3 chars)..." autocomplete="off" />
            <ul class="review-search-results" id="search-results"></ul>
          </div>
          <p class="review-error" id="modal-error"></p>
        </div>
      </div>

    </section>

    <script>
    (() => {{
      const API = {api_base!r};
      let adminKey = sessionStorage.getItem('adminKey') || '';
      let currentItem = null;
      let searchDebounce = null;

      const $ = id => document.getElementById(id);

      function headers() {{
        return {{'X-Admin-Key': adminKey, 'Content-Type': 'application/json'}};
      }}

      function showError(elId, msg) {{
        $(elId).textContent = msg;
      }}

      function clearError(elId) {{
        $(elId).textContent = '';
      }}

      // ── Key prompt ──────────────────────────────────────────────────────────

      async function tryUnlock(key) {{
        const res = await fetch(API + '?limit=1', {{headers: {{'X-Admin-Key': key}}}});
        if (res.ok) {{
          adminKey = key;
          sessionStorage.setItem('adminKey', key);
          $('review-key-prompt').style.display = 'none';
          $('review-queue-view').style.display = '';
          loadQueue();
        }} else {{
          showError('key-error', res.status === 401 || res.status === 403
            ? 'Invalid admin key.' : 'Server error. Try again.');
        }}
      }}

      $('key-form').addEventListener('submit', e => {{
        e.preventDefault();
        clearError('key-error');
        const key = $('admin-key-input').value.trim();
        if (key) tryUnlock(key);
      }});

      if (adminKey) {{
        $('review-key-prompt').style.display = 'none';
        $('review-queue-view').style.display = '';
        loadQueue();
      }}

      // ── Queue ───────────────────────────────────────────────────────────────

      async function loadQueue() {{
        const res = await fetch(API, {{headers: headers()}});
        if (res.status === 401 || res.status === 403) {{
          adminKey = '';
          sessionStorage.removeItem('adminKey');
          $('review-queue-view').style.display = 'none';
          $('review-key-prompt').style.display = '';
          showError('key-error', 'Session expired — re-enter admin key.');
          return;
        }}
        const data = await res.json();
        $('queue-heading').textContent = `Pending reviews (${{data.total_pending}})`;
        const list = $('queue-list');
        if (!data.items.length) {{
          list.innerHTML = '<p class="review-empty">No pending reviews.</p>';
          return;
        }}
        list.innerHTML = data.items.map(item => `
          <div class="review-queue-row" data-id="${{item.id}}" onclick="openModal(${{JSON.stringify(item)}})">
            <div class="review-row-title">${{escHtml(item.raw_title)}}</div>
            <div class="review-row-meta">
              <span class="review-meta-guess">${{item.best_guess_asset_name || '—'}}</span>
              <span class="review-meta-conf">${{item.best_guess_confidence != null ? (item.best_guess_confidence * 100).toFixed(0) + '%' : 'N/A'}}</span>
              <span class="review-meta-reason">${{escHtml(item.reason || '')}}</span>
            </div>
          </div>
        `).join('');
      }}

      $('refresh-btn').addEventListener('click', loadQueue);

      function escHtml(s) {{
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      }}

      // ── Modal ───────────────────────────────────────────────────────────────

      window.openModal = function(item) {{
        currentItem = item;
        $('modal-raw-title').textContent = item.raw_title;
        clearError('modal-error');
        $('override-search').style.display = 'none';
        $('override-input').value = '';
        $('search-results').innerHTML = '';

        const hasGuess = !!item.best_guess_asset_id;
        $('modal-meta').innerHTML = `
          <dl class="review-meta-dl">
            <dt>AI guess</dt><dd>${{item.best_guess_asset_name || '<em>No guess</em>'}}</dd>
            <dt>Confidence</dt><dd>${{item.best_guess_confidence != null ? (item.best_guess_confidence * 100).toFixed(0) + '%' : 'N/A'}}</dd>
            <dt>Reason</dt><dd>${{escHtml(item.reason || '')}}</dd>
          </dl>`;

        $('modal-actions').innerHTML = `
          <button class="button button-success" id="btn-accept" ${{hasGuess ? '' : 'disabled title="No best guess to accept"'}} onclick="resolveAccept()">Accept</button>
          <button class="button button-primary" id="btn-override" onclick="showOverride()">Override</button>
          <button class="button button-danger" id="btn-dismiss" onclick="resolveDismiss()">Dismiss</button>`;

        $('modal-backdrop').style.display = '';
      }};

      $('modal-close').addEventListener('click', () => {{
        $('modal-backdrop').style.display = 'none';
        currentItem = null;
      }});

      function setActionsDisabled(disabled) {{
        ['btn-accept','btn-override','btn-dismiss'].forEach(id => {{
          const el = $(id);
          if (el) el.disabled = disabled;
        }});
      }}

      async function resolveAccept() {{
        clearError('modal-error');
        setActionsDisabled(true);
        const res = await fetch(`${{API}}/${{currentItem.id}}/accept`, {{method:'POST', headers: headers()}});
        if (res.ok) {{ closeAndRefresh(); }} else {{
          const err = await res.json().catch(() => ({{detail: 'Request failed'}}));
          showError('modal-error', err.detail || 'Error');
          setActionsDisabled(false);
        }}
      }}

      window.showOverride = function() {{
        $('override-search').style.display = '';
        $('override-input').focus();
      }};

      $('override-input').addEventListener('input', e => {{
        clearTimeout(searchDebounce);
        const q = e.target.value.trim();
        if (q.length < 3) {{ $('search-results').innerHTML = ''; return; }}
        searchDebounce = setTimeout(() => searchAssets(q), 300);
      }});

      async function searchAssets(q) {{
        const res = await fetch(`${{API}}/assets/search?q=${{encodeURIComponent(q)}}`, {{headers: headers()}});
        if (!res.ok) return;
        const results = await res.json();
        $('search-results').innerHTML = results.length
          ? results.map(a => `<li class="search-result-item" onclick="resolveOverride('${{a.id}}','${{escHtml(a.name)}}')">${{escHtml(a.name)}}${{a.set_name ? ' · ' + escHtml(a.set_name) : ''}}</li>`).join('')
          : '<li class="search-result-empty">No results.</li>';
      }}

      window.resolveOverride = async function(assetId, assetName) {{
        clearError('modal-error');
        setActionsDisabled(true);
        const res = await fetch(`${{API}}/${{currentItem.id}}/override`, {{
          method: 'POST',
          headers: headers(),
          body: JSON.stringify({{asset_id: assetId}}),
        }});
        if (res.ok) {{ closeAndRefresh(); }} else {{
          const err = await res.json().catch(() => ({{detail: 'Request failed'}}));
          showError('modal-error', err.detail || 'Error');
          setActionsDisabled(false);
        }}
      }};

      async function resolveDismiss() {{
        clearError('modal-error');
        setActionsDisabled(true);
        const res = await fetch(`${{API}}/${{currentItem.id}}/dismiss`, {{method:'POST', headers: headers()}});
        if (res.ok) {{ closeAndRefresh(); }} else {{
          const err = await res.json().catch(() => ({{detail: 'Request failed'}}));
          showError('modal-error', err.detail || 'Error');
          setActionsDisabled(false);
        }}
      }}

      function closeAndRefresh() {{
        $('modal-backdrop').style.display = 'none';
        currentItem = null;
        loadQueue();
      }}
    }})();
    </script>
    """
    return _render_shell(
        title="Human Review Queue",
        current_path="/backstage/review",
        body=body,
        page_key="backstage_review",
        username=username,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```
python -m pytest tests/test_human_review_api.py::test_backstage_review_route_exists -v
```

Expected: `PASSED`.

- [ ] **Step 5: Smoke test app starts**

```
python -c "from backend.app.main import app; print('OK')"
```

Expected: `OK`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/site.py tests/test_human_review_api.py
git commit -m "feat: add /backstage/review HTML shell with JS queue, modal, and resolution flow"
```

---

## Task 4: CSS for review page

**Files:**
- Modify: `backend/app/static/site.css`

- [ ] **Step 1: Append styles to `backend/app/static/site.css`**

Add at the very end of the file:

```css
/* ── Human Review page ───────────────────────────────────────────────────── */

.review-page {
  max-width: 860px;
  margin: 0 auto;
  padding: 0 1rem 3rem;
  position: relative;
}

/* Key prompt */
.review-key-prompt {
  display: flex;
  justify-content: center;
  padding: 3rem 0;
}

.review-key-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 2rem;
  width: 100%;
  max-width: 400px;
}

.review-key-card h2 {
  margin: 0 0 0.5rem;
  font-size: 1.1rem;
}

.review-key-form {
  display: flex;
  gap: 0.5rem;
  margin-top: 1rem;
}

.review-key-form input {
  flex: 1;
  padding: 0.4rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 0.9rem;
  background: var(--bg);
  color: var(--text);
}

/* Queue */
.review-queue-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.review-queue-header h2 {
  margin: 0;
  font-size: 1rem;
}

.review-queue-row {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.75rem 1rem;
  margin-bottom: 0.5rem;
  cursor: pointer;
  transition: border-color 0.15s;
}

.review-queue-row:hover {
  border-color: var(--accent);
}

.review-row-title {
  font-weight: 600;
  font-size: 0.9rem;
  margin-bottom: 0.3rem;
}

.review-row-meta {
  display: flex;
  gap: 1rem;
  font-size: 0.78rem;
  color: var(--text-muted);
}

.review-meta-conf {
  font-variant-numeric: tabular-nums;
}

.review-empty {
  color: var(--text-muted);
  font-size: 0.9rem;
  padding: 2rem 0;
}

/* Modal */
.review-modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.review-modal {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1.75rem;
  width: 100%;
  max-width: 520px;
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.review-modal-close {
  position: absolute;
  top: 0.75rem;
  right: 0.75rem;
  background: none;
  border: none;
  font-size: 1rem;
  cursor: pointer;
  color: var(--text-muted);
}

.review-modal-label {
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  margin: 0;
}

.review-modal-title {
  font-family: monospace;
  font-size: 0.88rem;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.5rem 0.75rem;
  margin: 0;
  word-break: break-word;
}

.review-meta-dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.2rem 0.75rem;
  font-size: 0.82rem;
  margin: 0;
}

.review-meta-dl dt { color: var(--text-muted); }
.review-meta-dl dd { margin: 0; }

.review-modal-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.button-success {
  background: #22c55e;
  color: #fff;
  border: none;
}

.button-success:hover:not(:disabled) { background: #16a34a; }

.button-danger {
  background: #ef4444;
  color: #fff;
  border: none;
}

.button-danger:hover:not(:disabled) { background: #dc2626; }

button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* Override search */
.review-override-search {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.review-override-search input {
  padding: 0.4rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 0.88rem;
  background: var(--bg);
  color: var(--text);
}

.review-search-results {
  list-style: none;
  margin: 0;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 4px;
  max-height: 160px;
  overflow-y: auto;
  background: var(--surface);
}

.search-result-item {
  padding: 0.45rem 0.75rem;
  font-size: 0.82rem;
  cursor: pointer;
}

.search-result-item:hover { background: var(--bg); }

.search-result-empty {
  padding: 0.45rem 0.75rem;
  font-size: 0.82rem;
  color: var(--text-muted);
}

/* Errors */
.review-error {
  font-size: 0.82rem;
  color: #dc2626;
  min-height: 1.2em;
  margin: 0;
}
```

- [ ] **Step 2: Verify app still starts**

```
python -c "from backend.app.main import app; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/static/site.css
git commit -m "feat: add human review page CSS — queue, modal, key prompt, override search"
```

---

## Task 5: Run full test suite and push

- [ ] **Step 1: Run all review tests**

```
python -m pytest tests/test_human_review_api.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 2: Run existing tests to check for regressions**

```
python -m pytest tests/ -v -x
```

Expected: no failures.

- [ ] **Step 3: Final import verification**

```
python -c "
from backend.app.backstage.review_routes import router
from backend.app.models.human_review import HumanReviewQueue
row = HumanReviewQueue(raw_listing_id=__import__('uuid').uuid4(), raw_title='test')
print('resolution_type default:', row.resolution_type)
print('router prefix:', router.prefix)
print('All OK')
"
```

Expected:
```
resolution_type default: None
router prefix: /admin/review
All OK
```

- [ ] **Step 4: Push to GitHub**

```bash
git push origin main
```

---

## Self-Review

**Spec coverage:**
- ✅ Section 2 (auth): `require_admin_key` on all endpoints, `sessionStorage` key prompt in JS
- ✅ Section 3 (model): `resolution_type` column + migration 0008
- ✅ Section 4 (endpoints): list, accept, override, dismiss, assets/search all implemented
- ✅ Section 4 (list response): `total_pending`, `limit`, `offset` in `ReviewListResponse`
- ✅ Section 5 (accept): all 11 steps including listing status guard
- ✅ Section 5 (override): all 11 steps including listing status guard
- ✅ Section 5 (dismiss): all 7 steps including listing status guard, no price event
- ✅ Section 6 (errors): 404/409/422/500 guards all in `_load_unresolved`, `_load_pending_listing`, `_write_price_event`
- ✅ Section 7 (page layout): key prompt, queue view, modal with all fields, override search with 3-char min + debounce, Accept disabled when no guess
- ✅ Section 9 (out of scope): nothing extra added

**Placeholder scan:** None found.

**Type consistency:**
- `_load_unresolved` returns `HumanReviewQueue` — used in accept/override/dismiss ✅
- `_load_pending_listing` returns `RawListing` — used in all three resolution paths ✅
- `_write_price_event(db, asset_id: uuid.UUID, listing: RawListing)` — called correctly in accept/override ✅
- `mapping_cache.write(db, normalized_title, asset_id, confidence, method)` — matches `mapping_cache.py:23` signature ✅
- `ReviewListResponse.items` is `list[ReviewItem]` — built correctly in `list_review_items` ✅
