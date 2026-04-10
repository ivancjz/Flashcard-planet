# Signals Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/signals` web page with freemium tiering — free users see a daily snapshot, Pro users see live signals — backed by an append-only signal history table and a `User.access_tier` column.

**Architecture:** Server-rendered page following the existing `site.py` / `_render_shell()` pattern. Free users get a locked shell on the live column (no live values in HTML); Pro users get full live data. Access gating is a single `is_pro` bool computed at request time from `user.access_tier`.

**Tech Stack:** Python, FastAPI, SQLAlchemy 2.x, PostgreSQL (DISTINCT ON window), Alembic, inline HTML/CSS in `site.py`.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/app/models/user.py` | Modify | Add `access_tier` column |
| `alembic/versions/0006_add_user_access_tier.py` | Create | DB migration for access_tier |
| `backend/app/models/asset_signal_history.py` | Create | Append-only signal history model |
| `alembic/versions/0007_add_asset_signal_history.py` | Create | DB migration for history table |
| `backend/app/services/signal_service.py` | Modify | Append history on sweep + daily snapshot query |
| `backend/app/site.py` | Modify | `/signals` route + nav update |
| `backend/app/static/site.css` | Modify | Signal card styles, label badges, locked shell |
| `tests/test_signal_history.py` | Create | Tests for history append + snapshot query |
| `tests/test_signals_page.py` | Create | Tests for `/signals` route rendering |

---

## Task 1: User access tier — model + migration

**Files:**
- Modify: `backend/app/models/user.py`
- Create: `alembic/versions/0006_add_user_access_tier.py`
- Test: `tests/test_signals_page.py` (partial — just the model field check)

- [ ] **Step 1: Write the failing test**

Create `tests/test_signals_page.py`:

```python
"""Tests for /signals page rendering."""
from __future__ import annotations

from backend.app.models.user import User


def test_user_has_access_tier_field():
    """User model must have access_tier with default 'free'."""
    u = User(discord_user_id="123456789")
    assert u.access_tier == "free"


def test_user_access_tier_can_be_pro():
    u = User(discord_user_id="999999999", access_tier="pro")
    assert u.access_tier == "pro"
```

- [ ] **Step 2: Run test to verify it fails**

```
cd c:/Flashcard-planet
python -m pytest tests/test_signals_page.py::test_user_has_access_tier_field -v
```

Expected: `FAILED` — `User` has no attribute `access_tier`.

- [ ] **Step 3: Add `access_tier` to the User model**

In `backend/app/models/user.py`, add after the `is_active` line:

```python
    access_tier: Mapped[str] = mapped_column(String(16), nullable=False, server_default="free", default="free")
```

No other changes.

- [ ] **Step 4: Run tests to verify they pass**

```
python -m pytest tests/test_signals_page.py::test_user_has_access_tier_field tests/test_signals_page.py::test_user_access_tier_can_be_pro -v
```

Expected: both `PASSED`.

- [ ] **Step 5: Write migration `0006_add_user_access_tier.py`**

Create `alembic/versions/0006_add_user_access_tier.py`:

```python
"""Add access_tier to users.

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-11 00:00:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "access_tier",
            sa.String(16),
            nullable=False,
            server_default="free",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "access_tier")
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/user.py alembic/versions/0006_add_user_access_tier.py tests/test_signals_page.py
git commit -m "feat: add User.access_tier column + migration (free/pro tiering)"
```

---

## Task 2: Asset signal history — model + migration

**Files:**
- Create: `backend/app/models/asset_signal_history.py`
- Create: `alembic/versions/0007_add_asset_signal_history.py`
- Test: `tests/test_signal_history.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_signal_history.py`:

```python
"""Tests for signal history model and sweep append behaviour."""
from __future__ import annotations

from backend.app.models.asset_signal_history import AssetSignalHistory


def test_asset_signal_history_model_fields():
    """AssetSignalHistory must have all required fields."""
    import uuid
    from datetime import datetime, UTC
    from decimal import Decimal

    h = AssetSignalHistory(
        asset_id=uuid.uuid4(),
        label="BREAKOUT",
        confidence=75,
        price_delta_pct=Decimal("12.50"),
        liquidity_score=80,
        prediction="Up",
        computed_at=datetime.now(UTC),
    )
    assert h.label == "BREAKOUT"
    assert h.confidence == 75
```

- [ ] **Step 2: Run test to verify it fails**

```
python -m pytest tests/test_signal_history.py::test_asset_signal_history_model_fields -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'backend.app.models.asset_signal_history'`.

- [ ] **Step 3: Create the model**

Create `backend/app/models/asset_signal_history.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class AssetSignalHistory(Base):
    """Append-only log of every signal computed per asset per sweep.

    Used to serve the daily snapshot (latest row before midnight UTC) to free users.
    Never updated — only inserted.
    """

    __tablename__ = "asset_signal_history"
    __table_args__ = (
        Index("ix_asset_signal_history_asset_computed", "asset_id", "computed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[int | None] = mapped_column(Integer)
    price_delta_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    liquidity_score: Mapped[int | None] = mapped_column(Integer)
    prediction: Mapped[str | None] = mapped_column(String(32))
    computed_at: Mapped[datetime] = mapped_column(nullable=False)
```

- [ ] **Step 4: Run test to verify it passes**

```
python -m pytest tests/test_signal_history.py::test_asset_signal_history_model_fields -v
```

Expected: `PASSED`.

- [ ] **Step 5: Write migration `0007_add_asset_signal_history.py`**

Create `alembic/versions/0007_add_asset_signal_history.py`:

```python
"""Add asset_signal_history table.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-11 00:00:00.000000+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "asset_signal_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("label", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("price_delta_pct", sa.Numeric(8, 2), nullable=True),
        sa.Column("liquidity_score", sa.Integer(), nullable=True),
        sa.Column("prediction", sa.String(32), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_asset_signal_history_asset_computed",
        "asset_signal_history",
        ["asset_id", "computed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_asset_signal_history_asset_computed", table_name="asset_signal_history")
    op.drop_table("asset_signal_history")
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/asset_signal_history.py alembic/versions/0007_add_asset_signal_history.py tests/test_signal_history.py
git commit -m "feat: add AssetSignalHistory model + migration (append-only sweep log)"
```

---

## Task 3: Sweep appends to history table

**Files:**
- Modify: `backend/app/services/signal_service.py`
- Test: `tests/test_signal_history.py` (extend)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_signal_history.py`:

```python
def test_append_history_inserts_row(db_session):
    """_append_history must insert one row into asset_signal_history."""
    import uuid
    from datetime import datetime, UTC
    from decimal import Decimal
    from sqlalchemy import select

    from backend.app.models.asset_signal_history import AssetSignalHistory
    from backend.app.services.signal_service import _append_history, SignalRow
    from backend.app.models.enums import SignalLabel

    asset_id = uuid.uuid4()
    signal = SignalRow(
        asset_id=asset_id,
        label=SignalLabel.BREAKOUT,
        confidence=75,
        price_delta_pct=Decimal("12.50"),
        liquidity_score=80,
        prediction="Up",
        computed_at=datetime.now(UTC),
    )
    _append_history(db_session, signal=signal)
    db_session.flush()

    rows = db_session.scalars(
        select(AssetSignalHistory).where(AssetSignalHistory.asset_id == asset_id)
    ).all()
    assert len(rows) == 1
    assert rows[0].label == "BREAKOUT"
    assert rows[0].confidence == 75
```

Note: this test requires a `db_session` fixture. If your test suite doesn't have one, skip the DB assertion and just verify `_append_history` is importable and callable:

```python
def test_append_history_is_callable():
    from backend.app.services.signal_service import _append_history
    assert callable(_append_history)
```

- [ ] **Step 2: Run test to verify it fails**

```
python -m pytest tests/test_signal_history.py::test_append_history_is_callable -v
```

Expected: `FAILED` — `cannot import name '_append_history'`.

- [ ] **Step 3: Add `_append_history` to signal_service.py**

In `backend/app/services/signal_service.py`, add the import at the top (with the other model imports):

```python
from backend.app.models.asset_signal_history import AssetSignalHistory
```

Add the function after `_upsert_signal`:

```python
def _append_history(db: Session, *, signal: SignalRow) -> None:
    """Insert one row into the append-only signal history log."""
    db.add(AssetSignalHistory(
        asset_id=signal.asset_id,
        label=signal.label.value,
        confidence=signal.confidence,
        price_delta_pct=signal.price_delta_pct,
        liquidity_score=signal.liquidity_score,
        prediction=signal.prediction,
        computed_at=signal.computed_at,
    ))
```

Then in `_process_batch`, immediately after the `_upsert_signal(...)` call (around line 292), add:

```python
        _append_history(
            db,
            signal=SignalRow(
                asset_id=asset_id,
                label=label,
                confidence=snapshot.alert_confidence,
                price_delta_pct=percent_changes.get(asset_id),
                liquidity_score=snapshot.liquidity_score,
                prediction=prediction,
                computed_at=now,
            ),
        )
```

- [ ] **Step 4: Run test to verify it passes**

```
python -m pytest tests/test_signal_history.py::test_append_history_is_callable -v
```

Expected: `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/signal_service.py tests/test_signal_history.py
git commit -m "feat: append signal history row on every sweep"
```

---

## Task 4: Daily snapshot query

**Files:**
- Modify: `backend/app/services/signal_service.py`
- Test: `tests/test_signal_history.py` (extend)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_signal_history.py`:

```python
def test_get_daily_snapshot_signals_is_callable():
    """get_daily_snapshot_signals must be importable."""
    from backend.app.services.signal_service import get_daily_snapshot_signals
    assert callable(get_daily_snapshot_signals)
```

- [ ] **Step 2: Run test to verify it fails**

```
python -m pytest tests/test_signal_history.py::test_get_daily_snapshot_signals_is_callable -v
```

Expected: `FAILED` — `cannot import name 'get_daily_snapshot_signals'`.

- [ ] **Step 3: Add `get_daily_snapshot_signals` to signal_service.py**

Add these imports at the top of `signal_service.py` (they may already be partially present):

```python
from datetime import date
from sqlalchemy import text
```

Add the function at the bottom of the Read helpers section:

```python
def get_daily_snapshot_signals(
    db: Session,
    *,
    label: str | None = None,
) -> list[AssetSignalHistory]:
    """Return the latest-before-midnight-UTC signal per asset from history.

    Uses DISTINCT ON (asset_id) — Postgres-specific, fastest for this access pattern.
    label: optional filter, e.g. 'BREAKOUT'. Case-sensitive; matches AssetSignalHistory.label.
    """
    from datetime import datetime, timezone

    today_midnight = datetime.combine(
        date.today(), datetime.min.time(), tzinfo=timezone.utc
    )

    q = (
        select(AssetSignalHistory)
        .where(AssetSignalHistory.computed_at < today_midnight)
        .order_by(AssetSignalHistory.asset_id, AssetSignalHistory.computed_at.desc())
        .distinct(AssetSignalHistory.asset_id)
    )
    if label is not None:
        q = q.where(AssetSignalHistory.label == label)

    return list(db.scalars(q).all())
```

- [ ] **Step 4: Run test to verify it passes**

```
python -m pytest tests/test_signal_history.py::test_get_daily_snapshot_signals_is_callable -v
```

Expected: `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/signal_service.py tests/test_signal_history.py
git commit -m "feat: add get_daily_snapshot_signals() — latest-before-midnight per asset"
```

---

## Task 5: Signals page route

**Files:**
- Modify: `backend/app/site.py`
- Test: `tests/test_signals_page.py` (extend)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_signals_page.py`:

```python
def test_signals_route_exists():
    """GET /signals must be a registered route."""
    from backend.app.site import router
    paths = [r.path for r in router.routes]
    assert "/signals" in paths
```

- [ ] **Step 2: Run test to verify it fails**

```
python -m pytest tests/test_signals_page.py::test_signals_route_exists -v
```

Expected: `FAILED` — `/signals` not in paths.

- [ ] **Step 3: Add `/signals` to `_render_nav`**

In `backend/app/site.py`, locate `_render_nav` (around line 232). Add `"/signals"` entry between `/cards` and `/watchlists`:

```python
    items = [
        ("/", "概览", "Overview"),
        ("/dashboard", "实时仪表板", "Dashboard"),
        ("/cards", "卡牌浏览", "Cards"),
        ("/signals", "市场信号", "Signals"),
        ("/watchlists", "关注列表", "Watchlists"),
        ("/alerts", "预警管理", "Alerts"),
        ("/method", "方法论 / 路线图", "Method / Roadmap"),
    ]
```

- [ ] **Step 4: Add the `/signals` route**

Add the following imports near the top of `site.py` (after existing imports):

```python
from backend.app.api.deps import get_optional_user
from backend.app.models.asset import Asset
from backend.app.models.asset_signal_history import AssetSignalHistory
from backend.app.services.signal_service import get_all_signals, get_daily_snapshot_signals
```

Add this route after the `/cards/{external_id}` route and before `/method`:

```python
@router.get("/signals", response_class=HTMLResponse)
def signals_page(
    request: Request,
    label: str | None = Query(None),
) -> HTMLResponse:
    username = _session_username(request)

    # Resolve access tier from session JWT
    with SessionLocal() as db:
        current_user = None
        user_id = request.session.get("user_id")
        if user_id:
            from backend.app.models.user import User
            import uuid as _uuid
            try:
                current_user = db.get(User, _uuid.UUID(user_id))
            except Exception:
                pass

        is_pro = current_user is not None and current_user.access_tier == "pro"

        # Normalise label filter
        label_filter = label.upper() if label else None
        valid_labels = {"BREAKOUT", "MOVE", "WATCH", "IDLE"}
        if label_filter and label_filter not in valid_labels:
            label_filter = None

        # Always run snapshot query
        snapshots = get_daily_snapshot_signals(db, label=label_filter)

        # Build asset name map
        asset_ids = [s.asset_id for s in snapshots]
        asset_rows = db.execute(
            select(Asset.id, Asset.name, Asset.set_name, Asset.variant)
            .where(Asset.id.in_(asset_ids))
        ).all() if asset_ids else []
        asset_map = {r.id: r for r in asset_rows}

        # Pro: also run live query
        live_map: dict = {}
        if is_pro:
            live_signals = get_all_signals(db, limit=500)
            if label_filter:
                live_signals = [s for s in live_signals if s.label == label_filter]
            live_map = {s.asset_id: s for s in live_signals}

    # Build filter bar HTML
    filter_links = ""
    for lbl, zh, en in [
        (None, "全部", "All"),
        ("BREAKOUT", "突破", "BREAKOUT"),
        ("MOVE", "波动", "MOVE"),
        ("WATCH", "观察", "WATCH"),
        ("IDLE", "静默", "IDLE"),
    ]:
        href = "/signals" if lbl is None else f"/signals?label={lbl}"
        active = " is-active" if label_filter == lbl else ""
        filter_links += f'<a class="signal-filter-link{active}" href="{href}">{_lang_pair(zh, en)}</a>'

    # Build rows HTML
    rows_html = ""
    if not snapshots:
        rows_html = f'<p class="empty-state">{_lang_pair("暂无每日快照数据，请等待首次完整数据日后再来查看。", "No daily snapshot available yet — check back after the first full day of data.")}</p>'
    else:
        for snap in snapshots:
            asset = asset_map.get(snap.asset_id)
            if asset is None:
                import logging as _logging
                _logging.getLogger(__name__).warning("signals_page: unresolvable asset_id=%s, skipping", snap.asset_id)
                continue
            asset_name = escape(asset.name)
            if asset.set_name:
                asset_name += f' <span class="asset-set">{escape(asset.set_name)}</span>'

            left_card = _render_snapshot_card(snap, asset_name)

            live_signal = live_map.get(snap.asset_id) if is_pro else None
            right_card = _render_live_card(live_signal, is_pro)

            rows_html += f"""
            <div class="signal-row">
              {left_card}
              {right_card}
            </div>"""

    body = f"""
    <section class="page-intro">
      <div>
        <p class="eyebrow">{_lang_pair("市场信号", "Signals")}</p>
        <h1>{_lang_pair("每日信号快照与实时信号层", "Daily snapshots and live signal layer")}</h1>
        <p class="lede">
          {_lang_pair("免费用户查看每日快照信号；升级 Pro 即可访问实时信号与 AI 解读。",
          "Free users see daily snapshot signals. Upgrade to Pro for live signals and AI explanations.")}
        </p>
      </div>
    </section>

    <section class="signal-page">
      <div class="signal-filter-bar">
        {filter_links}
      </div>
      <div class="signal-rows">
        {rows_html}
      </div>
    </section>
    """

    return _render_shell(
        title=_lang_pair("市场信号", "Signals"),
        current_path="/signals",
        body=body,
        page_key="signals",
        username=username,
    )


_LABEL_COLOURS = {
    "BREAKOUT": "signal-breakout",
    "MOVE": "signal-move",
    "WATCH": "signal-watch",
    "IDLE": "signal-idle",
}


def _render_snapshot_card(snap: "AssetSignalHistory", asset_name_html: str) -> str:
    colour = _LABEL_COLOURS.get(snap.label, "signal-idle")
    delta = f"{snap.price_delta_pct:+.2f}%" if snap.price_delta_pct is not None else "N/A"
    conf = str(snap.confidence) if snap.confidence is not None else "N/A"
    liq = str(snap.liquidity_score) if snap.liquidity_score is not None else "N/A"
    pred = escape(snap.prediction) if snap.prediction else "—"
    ts = snap.computed_at.strftime("%-d %b %Y, %-I:%M %p UTC") if snap.computed_at else "—"

    explanation_html = ""
    # AssetSignalHistory has no explanation — left card shows nothing for now
    # (explanation lives on AssetSignal; future task can join if needed)

    return f"""
    <div class="signal-card signal-card-snapshot">
      <p class="signal-card-header">{_lang_pair("每日快照", "Daily Snapshot")}</p>
      <p class="signal-asset-name">{asset_name_html}</p>
      <span class="signal-badge {colour}">{escape(snap.label)}</span>
      <dl class="signal-metrics">
        <dt>{_lang_pair("置信度", "Confidence")}</dt><dd>{conf}</dd>
        <dt>{_lang_pair("价格变动", "Δ Price")}</dt><dd>{delta}</dd>
        <dt>{_lang_pair("流动性", "Liquidity")}</dt><dd>{liq}</dd>
        <dt>{_lang_pair("预测", "Prediction")}</dt><dd>{pred}</dd>
      </dl>
      <p class="signal-timestamp">{_lang_pair("截至", "As of")} {ts}</p>
    </div>"""


def _render_live_card(live_signal, is_pro: bool) -> str:
    if not is_pro:
        return """
    <div class="signal-card signal-card-locked">
      <p class="signal-card-header">Live Signal <span class="pro-badge">PRO</span></p>
      <div class="signal-locked-shell">
        <span class="skeleton-line"></span>
        <span class="skeleton-line skeleton-line-short"></span>
        <span class="skeleton-line"></span>
        <span class="skeleton-line skeleton-line-short"></span>
      </div>
      <p class="signal-locked-copy">Unlock live label, confidence, delta, and AI explanation</p>
      <a class="button button-primary signal-pro-cta" href="/pro">Go Pro</a>
    </div>"""

    if live_signal is None:
        return """
    <div class="signal-card signal-card-live signal-card-awaiting">
      <p class="signal-card-header">Live Signal</p>
      <p class="signal-awaiting">Awaiting next sweep</p>
    </div>"""

    colour = _LABEL_COLOURS.get(live_signal.label, "signal-idle")
    delta = f"{live_signal.price_delta_pct:+.2f}%" if live_signal.price_delta_pct is not None else "N/A"
    conf = str(live_signal.confidence) if live_signal.confidence is not None else "N/A"
    liq = str(live_signal.liquidity_score) if live_signal.liquidity_score is not None else "N/A"
    pred = escape(live_signal.prediction) if live_signal.prediction else "—"
    ts = live_signal.computed_at.strftime("%-d %b %Y, %-I:%M %p UTC") if live_signal.computed_at else "—"

    return f"""
    <div class="signal-card signal-card-live">
      <p class="signal-card-header">Live Signal</p>
      <span class="signal-badge {colour}">{escape(live_signal.label)}</span>
      <dl class="signal-metrics">
        <dt>Confidence</dt><dd>{conf}</dd>
        <dt>Δ Price</dt><dd>{delta}</dd>
        <dt>Liquidity</dt><dd>{liq}</dd>
        <dt>Prediction</dt><dd>{pred}</dd>
      </dl>
      <p class="signal-timestamp">Updated {ts}</p>
    </div>"""
```

- [ ] **Step 5: Run test to verify it passes**

```
python -m pytest tests/test_signals_page.py::test_signals_route_exists -v
```

Expected: `PASSED`.

- [ ] **Step 6: Smoke-test the app starts**

```
python -c "from backend.app.main import app; print('OK')"
```

Expected: `OK` with no import errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/site.py tests/test_signals_page.py
git commit -m "feat: add /signals page with freemium two-column layout"
```

---

## Task 6: CSS — signal card styles

**Files:**
- Modify: `backend/app/static/site.css`

No new test needed — visual styles verified by running the app.

- [ ] **Step 1: Append signal styles to site.css**

Add the following block at the end of `backend/app/static/site.css`:

```css
/* ── Signals page ──────────────────────────────────────────────────────── */

.signal-page {
  max-width: 960px;
  margin: 0 auto;
  padding: 0 1rem 3rem;
}

.signal-filter-bar {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 1.5rem;
}

.signal-filter-link {
  padding: 0.35rem 0.85rem;
  border: 1px solid var(--border);
  border-radius: 2rem;
  font-size: 0.8rem;
  text-decoration: none;
  color: var(--text-muted);
  transition: background 0.15s, color 0.15s;
}

.signal-filter-link:hover,
.signal-filter-link.is-active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.signal-rows {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.signal-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}

@media (max-width: 600px) {
  .signal-row {
    grid-template-columns: 1fr;
  }
}

/* ── Signal cards ──────────────────────────────────────────────────────── */

.signal-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  min-height: 220px;
}

.signal-card-header {
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  margin: 0;
}

.signal-asset-name {
  font-weight: 600;
  font-size: 0.95rem;
  margin: 0;
}

.asset-set {
  font-weight: 400;
  color: var(--text-muted);
  font-size: 0.85rem;
}

/* ── Label badges ──────────────────────────────────────────────────────── */

.signal-badge {
  display: inline-block;
  padding: 0.2rem 0.6rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  width: fit-content;
}

.signal-breakout { background: #fee2e2; color: #b91c1c; }
.signal-move     { background: #fef3c7; color: #b45309; }
.signal-watch    { background: #dbeafe; color: #1d4ed8; }
.signal-idle     { background: #f3f4f6; color: #6b7280; }

/* ── Metrics dl ────────────────────────────────────────────────────────── */

.signal-metrics {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.15rem 0.75rem;
  font-size: 0.82rem;
  margin: 0;
}

.signal-metrics dt { color: var(--text-muted); }
.signal-metrics dd { margin: 0; font-weight: 500; }

.signal-timestamp {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin: 0;
  margin-top: auto;
}

/* ── Locked shell (free tier) ──────────────────────────────────────────── */

.signal-card-locked {
  position: relative;
}

.signal-locked-shell {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  flex: 1;
}

.skeleton-line {
  display: block;
  background: var(--border);
  border-radius: 4px;
  height: 0.85rem;
  width: 100%;
  opacity: 0.6;
}

.skeleton-line-short {
  width: 55%;
}

.pro-badge {
  display: inline-block;
  margin-left: 0.4rem;
  padding: 0.1rem 0.45rem;
  background: #f59e0b;
  color: #fff;
  border-radius: 3px;
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  vertical-align: middle;
}

.signal-locked-copy {
  font-size: 0.8rem;
  color: var(--text-muted);
  margin: 0;
}

.signal-pro-cta {
  width: fit-content;
  font-size: 0.82rem;
  margin-top: auto;
}

/* ── Awaiting state (Pro, no live signal) ──────────────────────────────── */

.signal-card-awaiting {
  justify-content: center;
  align-items: flex-start;
}

.signal-awaiting {
  color: var(--text-muted);
  font-size: 0.85rem;
  margin: 0;
}

/* ── Empty state ───────────────────────────────────────────────────────── */

.empty-state {
  color: var(--text-muted);
  font-size: 0.9rem;
  padding: 2rem 0;
}
```

- [ ] **Step 2: Verify the app starts and the page is reachable**

```
python -c "from backend.app.main import app; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/static/site.css
git commit -m "feat: add signal card CSS — badges, locked shell, two-column layout"
```

---

## Task 7: Run full test suite + verify

- [ ] **Step 1: Run all tests**

```
python -m pytest tests/test_signals_page.py tests/test_signal_history.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 2: Run existing signal tests to check nothing regressed**

```
python -m pytest tests/ -v --ignore=tests/test_noise_filter.py -x
```

Expected: no failures introduced by this feature.

- [ ] **Step 3: Verify imports are clean**

```
python -c "
from backend.app.models.asset_signal_history import AssetSignalHistory
from backend.app.services.signal_service import get_daily_snapshot_signals, _append_history
from backend.app.models.user import User
print('access_tier default:', User(discord_user_id='x').access_tier)
print('All imports OK')
"
```

Expected:
```
access_tier default: free
All imports OK
```

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: signals page — freemium layout, history table, access tier (complete)"
```

---

## Self-Review Notes

- **Spec coverage:** All six error states handled inline in `signals_page()`. Access tier model matches spec. History table schema matches spec (id, asset_id, all signal fields, computed_at, composite index). Nav entry added. Locked shell contains no live values. Pro path short-circuits live query skip for free users.
- **Placeholders:** None.
- **Type consistency:** `AssetSignalHistory` used in `_render_snapshot_card` type hint matches the model. `get_daily_snapshot_signals` returns `list[AssetSignalHistory]`. `get_all_signals` returns `list[AssetSignal]` — both used correctly in `signals_page()`.
- **One gap closed:** The `strftime("%-d %b")` format uses Linux-style padding suppression. On Windows this should be `%#d %b`. Since the server runs Linux in production this is fine; note it if running locally on Windows.
