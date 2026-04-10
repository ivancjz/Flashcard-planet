# Signals Page Design

**Date:** 2026-04-11
**Status:** Approved
**Scope:** `/signals` web page with freemium tiering, signal history table, and access tier model

---

## 1. Overview

Add a public `/signals` page to Flashcard Planet that displays trading card market signals (BREAKOUT / MOVE / WATCH / IDLE) in a two-column layout: a free Daily Snapshot column and a gated Live Signal — Pro column. The backend signal detection system is already complete; this spec covers the new storage, access tier, and presentation layer.

---

## 2. Access Tier Model

### `User.access_tier`

Add a single `String(16)` column to the existing `users` table:

- Column: `access_tier`
- Type: `VARCHAR(16) NOT NULL DEFAULT 'free'`
- Valid values: `"free"`, `"pro"`
- Set manually (direct DB update or future admin route) for MVP
- Stripe subscription replaces the unlock mechanism later without changing any product logic — the tier check always reads `user.access_tier == "pro"`

### Migration

New Alembic migration `0006_add_user_access_tier.py` adds the column.

### Access check (computed once per request)

```python
is_pro = current_user is not None and current_user.access_tier == "pro"
```

Unauthenticated users are treated identically to free users (`is_pro = False`).

---

## 3. Signal History Table

### Purpose

`asset_signals` is a one-row-per-asset upsert table. To serve "latest signal before midnight UTC" per asset, we need an append-only history log.

### Schema: `asset_signal_history`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | default uuid4 |
| `asset_id` | UUID FK → assets.id | not null, indexed |
| `label` | VARCHAR(32) | not null |
| `confidence` | INTEGER | nullable |
| `price_delta_pct` | NUMERIC(8,2) | nullable |
| `liquidity_score` | INTEGER | nullable |
| `prediction` | VARCHAR(32) | nullable |
| `computed_at` | TIMESTAMP | not null — copied from the sweep timestamp |

**Index:** `(asset_id, computed_at DESC)` — required for the daily snapshot query.

**Migration:** `0007_add_asset_signal_history.py`

### Write path

The signal sweep (`sweep_signals` in `signal_service.py`) writes to both tables on every run:
1. Upsert into `asset_signals` (existing behaviour, unchanged)
2. Append a new row into `asset_signal_history`

No deduplication — every sweep produces one history row per asset.

---

## 4. Page Layout

### Navigation

Add `/signals` to `_render_nav()` in `site.py`, between "Cards" and "Watchlists":

```
概览 · 实时仪表板 · 卡牌浏览 · 信号 · 关注列表 · 预警管理 · 方法论
Overview · Dashboard · Cards · Signals · Watchlists · Alerts · Method
```

### URL

`GET /signals` — optional query param `?label=BREAKOUT|MOVE|WATCH|IDLE` for label filtering.

### Page structure

```
[page-intro section]
  Eyebrow: "市场信号 / Signals"
  H1: "每日信号快照与实时信号层 / Daily snapshots and live signal layer"
  Lede: brief explanation of free vs pro

[filter bar]
  All | BREAKOUT | MOVE | WATCH | IDLE

[signal rows — one per asset with a snapshot]
  [row]
    [Daily Snapshot card — always visible]
    [Live Signal card — Pro content or locked shell]
```

### Signal row — two cards side by side

**Left card: Daily Snapshot**
- Header: "Daily Snapshot"
- Asset name (name + set_name + variant where available)
- Label badge (colour-coded)
- Confidence, Δ%, liquidity score, prediction
- Timestamp: "As of Apr 10, 11:47 PM UTC"
- Expandable AI explanation section (if `explanation` exists on the snapshot row)

**Right card: Live Signal — Pro user**
- Header: "Live Signal"
- Same fields as left card, sourced from `asset_signals`
- Current `computed_at` timestamp
- Expandable AI explanation (if available)

**Right card: Live Signal — free user (locked shell)**
- Header: "Live Signal"
- Pro badge
- 3 skeleton placeholder lines (CSS, no real values)
- Copy: "Unlock live label, confidence, delta, and AI explanation"
- CTA button: "Go Pro"
- No live values in the HTML source — server never sends them to free users

**Right card: Pro user, no live signal (awaiting)**
- Header: "Live Signal"
- No CTA
- Message: "Awaiting next sweep"
- Same card height as a populated card

### Label badge colours

| Label | Colour |
|---|---|
| BREAKOUT | Red |
| MOVE | Amber |
| WATCH | Blue |
| IDLE | Grey |

### Visual alignment

Locked shell cards must occupy the same height as a populated live card to keep rows visually balanced. Achieved via min-height CSS on the card, matching skeleton line count to the real card's field count.

---

## 5. Data Flow

### Request handling (per page load)

1. Resolve `current_user` from session/token (nullable — unauthenticated is allowed)
2. Compute `is_pro`
3. Compute `today_midnight_utc = date_trunc('day', now() AT TIME ZONE 'UTC')`
4. Run **daily snapshot query** (always): latest row per asset in `asset_signal_history` where `computed_at < today_midnight_utc`, filtered by `?label` if present. Uses `DISTINCT ON (asset_id) ORDER BY asset_id, computed_at DESC`.
5. If `is_pro`: run **live query** — current rows from `asset_signals`, filtered by same label.
6. **Merge:** iterate over snapshot rows (source of truth). For each snapshot row, look up `live_signal` by `asset_id` from the live results dict. Build list of `(asset, snapshot_signal, live_signal_or_none)` tuples.
7. Render template. Pass `is_pro` to template. If `is_pro=False`, `live_signal` is always `None` — locked shell renders regardless.

### Filtering semantics

`?label=BREAKOUT` filters the snapshot query. Pro live query uses the same filter. A free user filtering by BREAKOUT sees only assets whose *daily snapshot* label is BREAKOUT — the live label is never revealed.

---

## 6. Error States

| Condition | Behaviour |
|---|---|
| History table empty (first deploy) | Empty state: "No daily snapshot available yet — check back after the first full day of data." |
| Asset has live signal but no snapshot | Asset excluded from page entirely. Snapshot rows are the source of truth. |
| Asset has snapshot, no live signal — free user | Left card renders normally. Right card: standard locked Pro shell. |
| Asset has snapshot, no live signal — Pro user | Left card renders normally. Right card: "Awaiting next sweep" placeholder, same height. |
| Sweep hasn't run today | Pro users see live card with older `computed_at` timestamp. No special recovery for MVP. |
| Asset snapshot references unresolvable asset | Skip that row silently. Log warning server-side. Do not crash the page. |
| User not logged in | Treated as free. No live query. Locked shell on right. |

---

## 7. Out of Scope (this iteration)

- Stripe subscription integration (access_tier is set manually for MVP)
- Row-level asset name header above the two cards (future layout refinement)
- Signal history trend arrows / label-change indicators (requires querying history depth)
- Pro-only AI explanation on the live card calling the `/explain` endpoint on demand (can be added after page ships)
- Pagination (no hard row limit for MVP; add pagination when asset count makes it necessary)

---

## 8. Files Changed

| File | Change |
|---|---|
| `backend/app/models/user.py` | Add `access_tier: Mapped[str]` column |
| `alembic/versions/0006_add_user_access_tier.py` | New migration |
| `backend/app/models/asset_signal_history.py` | New model |
| `alembic/versions/0007_add_asset_signal_history.py` | New migration |
| `backend/app/services/signal_service.py` | Append to history on every sweep |
| `backend/app/site.py` | New `/signals` route + `_render_nav` update |
| `backend/app/static/site.css` | Signal card styles, label badges, locked shell, skeleton lines |
