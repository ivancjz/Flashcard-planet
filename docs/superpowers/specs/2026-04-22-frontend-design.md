# Flashcard Planet — Full-Stack Frontend Design
**Date:** 2026-04-22  
**Status:** Approved by user  
**Approach:** SPA-first with mock adapter → real API swap

---

## Decisions Made

| Question | Decision |
|---|---|
| SSR vs SPA | Replace SSR entirely. React SPA becomes the sole frontend. |
| Signal labels | Use real labels: BREAKOUT / MOVE / WATCH / IDLE / INSUFFICIENT_DATA |
| Scope | Full-stack: new FastAPI web endpoints + React SPA |
| Build order | SPA-first with typed mock layer; swap to real API per endpoint |

---

## Section 1 — Directory Layout

```
flashcard-planet/
  frontend/                        ← scaffold (Vite + React + TS)
    src/
      api/
        api.ts                     ← single adapter: one function per endpoint
      components/
        NavBar.tsx
        TickerBar.tsx
        Sparkline.tsx
        CardArt.tsx
        SignalBadge.tsx
      pages/
        LandingPage.tsx
        DashboardPage.tsx
        CardDetailPage.tsx
        AlertsPage.tsx
      styles/
        theme.css                  ← design tokens
      lib/
        utils.ts                   ← typeToColor, relativeTime, localStorage helpers, signalToMeta
        mockData.ts                ← typed mock data
      types/
        api.ts                     ← all TypeScript types (defined first)
    index.html
    vite.config.ts
  backend/
    app/
      api/routes/
        web.py                     ← new: web-specific public endpoints
      site.py                      ← gutted: remove SSR, add SPA catch-all
      main.py                      ← mount frontend/dist as StaticFiles
```

---

## Section 2 — Step Sequence

Follow this order exactly. Do not start a later step before the earlier one compiles cleanly.

1. Scaffold `frontend/` — Vite + React + TS, install React Router v6, no other dependencies
2. Write `src/types/api.ts` — all types first; everything else imports from here
3. Write `src/lib/mockData.ts` — mock data conforming exactly to the types
4. Write `src/api/api.ts` — all functions returning mocks, typed return values
5. Write `src/lib/utils.ts` — `typeToColor`, `relativeTime`, `getReadAlertIds`, `markAlertRead`, `markAllAlertsRead`, `signalToMeta`
6. Write `src/styles/theme.css` — design tokens (Section 4)
7. Build components — NavBar, TickerBar, Sparkline, CardArt, SignalBadge
8. Build pages — LandingPage, DashboardPage, CardDetailPage, AlertsPage
9. Wire routing in `main.tsx` with React Router v6
10. **Verify:** `npm run dev` — all 4 pages render with mock data, zero TS errors, zero console errors
11. Write `backend/app/api/routes/web.py` — all 5 endpoints (Section 6)
12. Update `backend/app/main.py` — mount `frontend/dist`, register web router
13. Update `backend/app/site.py` — remove SSR routes, add SPA catch-all
14. Swap `api.ts` functions — one at a time; `curl` each endpoint before swapping
15. **Final verify:** `npm run build && uvicorn` — full stack end-to-end

---

## Section 3 — Types (`src/types/api.ts`)

```typescript
// Real signal labels from the DB — do not rename or alias
export type Signal = 'BREAKOUT' | 'MOVE' | 'WATCH' | 'IDLE' | 'INSUFFICIENT_DATA'

export type Rarity = 'common' | 'uncommon' | 'rare' | 'holo' | 'ultra' | 'secret'

export interface MarketStats {
  total_assets: number
  signal_counts: Record<Signal, number>   // { BREAKOUT: 2, MOVE: 5, ... }
  last_ingest_utc: string | null          // ISO timestamp
  next_ingest_utc: string | null          // null for now
  sources_active: string[]                // ["pokemon_tcg_api", "ebay_sold"]
}

export interface TickerItem {
  asset_id: string           // UUID as string
  name: string
  price_delta_pct: number
  signal: Signal
  current_price: number | null   // from latest price_history row
}

export interface CardSummary {
  asset_id: string           // UUID as string
  name: string
  set_name: string | null
  rarity: Rarity | null
  card_type: string | null   // e.g. "Fire", "Dark" — from assets.category or metadata
  tcg_price: number | null   // latest price_history WHERE source='pokemon_tcg_api'
  ebay_price: number | null  // latest price_history WHERE source='ebay_sold'
  signal: Signal
  price_delta_pct: number | null
  liquidity_score: number | null
  volume_24h: number | null  // count of ebay_sold rows in last 24h
  image_url: string | null
}

export interface PricePoint {
  date: string             // "2024-01-15"
  tcg_price: number | null
  ebay_price: number | null
}

export interface CardDetail extends CardSummary {
  price_history: PricePoint[]     // last 30 days from price_history table
  spread_pct: number | null       // (tcg - ebay) / tcg * 100
}

// Alerts come from asset_signal_history (append-only snapshot table).
// Transitions are found via LAG() — rows where label changed from previous.
// Read state is client-side only via localStorage.
export interface AlertEvent {
  id: string                       // UUID
  asset_id: string
  card_name: string
  previous_signal: Signal | null   // LAG(label) — null if first ever signal
  current_signal: Signal
  price_delta_pct: number | null
  created_at: string               // ISO timestamp (computed_at)
  severity: 'high' | 'medium' | 'low'  // BREAKOUT=high, MOVE=medium, else low
}

export interface AlertsResponse {
  alerts: AlertEvent[]
  total: number
}

export interface CardsResponse {
  cards: CardSummary[]
  total: number
  limit: number
  offset: number
}
```

---

## Section 4 — Design System (`src/styles/theme.css`)

```css
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=Space+Mono:ital,wght@0,400;0,700;1,400&family=Inter:wght@300;400;500;600&display=swap');

:root {
  --bg-base: #0c0c10;
  --bg-surface: #13131a;
  --bg-elevated: #1a1a24;
  --bg-hover: #20202e;
  --border-subtle: #1e1e2e;
  --border-default: #2a2a3e;
  --border-strong: #3a3a58;
  --gold: #f0b429;
  --gold-dim: #c48a10;
  --gold-glow: rgba(240, 180, 41, 0.12);
  --breakout: #22c55e;
  --breakout-bg: rgba(34, 197, 94, 0.08);
  --breakout-border: rgba(34, 197, 94, 0.25);
  --move: #f59e0b;
  --move-bg: rgba(245, 158, 11, 0.08);
  --move-border: rgba(245, 158, 11, 0.25);
  --watch: #fb923c;
  --watch-bg: rgba(251, 146, 60, 0.08);
  --watch-border: rgba(251, 146, 60, 0.25);
  --idle: #64748b;
  --idle-bg: rgba(100, 116, 139, 0.08);
  --idle-border: rgba(100, 116, 139, 0.2);
  --nodata: #3a3a58;
  --text-primary: #e8e8f0;
  --text-secondary: #8888a8;
  --text-muted: #48485e;
  --text-inverse: #0c0c10;
  --font-display: 'Syne', sans-serif;
  --font-mono: 'Space Mono', monospace;
  --font-body: 'Inter', sans-serif;
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 14px;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg-base); color: var(--text-primary); font-family: var(--font-body); -webkit-font-smoothing: antialiased; }
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: var(--bg-surface); }
::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 3px; }
.surface { background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: var(--radius-lg); }
.btn { font-family: var(--font-display); font-weight: 600; font-size: 13px; letter-spacing: 0.02em; padding: 9px 20px; border-radius: var(--radius-sm); border: none; cursor: pointer; transition: all 0.15s ease; display: inline-flex; align-items: center; gap: 6px; }
.btn-primary { background: var(--gold); color: var(--text-inverse); }
.btn-primary:hover { background: #f5c030; transform: translateY(-1px); box-shadow: 0 6px 24px var(--gold-glow); }
.btn-ghost { background: transparent; color: var(--text-secondary); border: 1px solid var(--border-default); }
.btn-ghost:hover { background: var(--bg-elevated); color: var(--text-primary); border-color: var(--border-strong); }
.btn-sm { font-size: 12px; padding: 6px 13px; }
.nav { position: sticky; top: 0; z-index: 100; background: rgba(12,12,16,0.88); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border-bottom: 1px solid var(--border-subtle); padding: 0 28px; height: 60px; display: flex; align-items: center; justify-content: space-between; gap: 24px; }
.nav-logo { font-family: var(--font-display); font-weight: 800; font-size: 17px; color: var(--gold); cursor: pointer; letter-spacing: -0.03em; display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.nav-logo-sub { color: var(--text-muted); font-weight: 400; font-size: 12px; }
.nav-links { display: flex; align-items: center; gap: 2px; }
.nav-link { font-size: 13px; font-weight: 500; color: var(--text-secondary); padding: 6px 14px; border-radius: var(--radius-sm); cursor: pointer; transition: all 0.12s; border: 1px solid transparent; }
.nav-link:hover { color: var(--text-primary); background: var(--bg-elevated); }
.nav-link.active { color: var(--gold); background: var(--gold-glow); border-color: rgba(240,180,41,0.18); }
.badge { font-family: var(--font-mono); font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 4px; letter-spacing: 0.04em; text-transform: uppercase; display: inline-flex; align-items: center; gap: 4px; }
.badge-breakout { background: var(--breakout-bg); color: var(--breakout); border: 1px solid var(--breakout-border); }
.badge-move     { background: var(--move-bg);     color: var(--move);     border: 1px solid var(--move-border); }
.badge-watch    { background: var(--watch-bg);    color: var(--watch);    border: 1px solid var(--watch-border); }
.badge-idle     { background: var(--idle-bg);     color: var(--idle);     border: 1px solid var(--idle-border); }
.badge-nodata   { background: transparent; color: var(--text-muted); border: 1px dashed var(--nodata); }
.up   { color: var(--breakout); font-family: var(--font-mono); font-size: 12px; }
.down { color: #ef4444;         font-family: var(--font-mono); font-size: 12px; }
.ticker-bar { background: var(--bg-surface); border-bottom: 1px solid var(--border-subtle); padding: 7px 0; overflow: hidden; }
.ticker-inner { display: flex; gap: 48px; animation: ticker-scroll 30s linear infinite; white-space: nowrap; width: max-content; }
@keyframes ticker-scroll { from { transform: translateX(0); } to { transform: translateX(-50%); } }
@keyframes fade-up { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: translateY(0); } }
.fade-up   { animation: fade-up 0.45s ease both; }
.fade-up-1 { animation: fade-up 0.45s 0.06s ease both; }
.fade-up-2 { animation: fade-up 0.45s 0.12s ease both; }
.fade-up-3 { animation: fade-up 0.45s 0.18s ease both; }
.fade-up-4 { animation: fade-up 0.45s 0.24s ease both; }
@keyframes float { 0%,100% { transform: translateY(0) rotate(-1.5deg); } 50% { transform: translateY(-12px) rotate(1.5deg); } }
.float   { animation: float 5.0s ease-in-out infinite; }
.float-2 { animation: float 5.5s 1.6s ease-in-out infinite; }
.float-3 { animation: float 4.8s 3.2s ease-in-out infinite; }
@keyframes shine { 0% { background-position: -200% center; } 100% { background-position: 200% center; } }
.holo { position: relative; overflow: hidden; }
.holo::after { content: ''; position: absolute; inset: 0; background: linear-gradient(105deg, transparent 40%, rgba(255,255,255,0.05) 50%, transparent 60%); background-size: 200% 100%; animation: shine 4s ease-in-out infinite; pointer-events: none; border-radius: inherit; }
@keyframes pulse-dot { 0%,100% { opacity: 1; } 50% { opacity: 0.3; } }
.pulse-dot { animation: pulse-dot 1.8s ease-in-out infinite; }
@keyframes skeleton-pulse { 0%,100% { opacity: 0.4; } 50% { opacity: 0.7; } }
.skeleton { background: var(--bg-elevated); border-radius: var(--radius-sm); animation: skeleton-pulse 1.5s ease-in-out infinite; }
.page-content { max-width: 1180px; margin: 0 auto; padding: 28px 28px 64px; }
.page-title    { font-family: var(--font-display); font-weight: 700; font-size: 22px; letter-spacing: -0.02em; }
.page-subtitle { font-size: 11px; color: var(--text-muted); font-family: var(--font-mono); letter-spacing: 0.08em; text-transform: uppercase; margin-top: 3px; }
```

---

## Section 5 — API Adapter (`src/api/api.ts`)

Each function starts returning mocks. Swap body when real endpoint is ready — signature and return type never change.

```typescript
import type { MarketStats, TickerItem, CardsResponse, CardDetail, AlertsResponse, Signal } from '../types/api'
import { MOCK_STATS, MOCK_TICKER, MOCK_CARDS, MOCK_PRICE_HISTORY, MOCK_ALERTS } from '../lib/mockData'
import { getReadAlertIds } from '../lib/utils'

const BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export async function fetchStats(): Promise<MarketStats> {
  // TODO: swap → fetch(`${BASE}/api/v1/web/stats`).then(r => r.json())
  return MOCK_STATS
}

export async function fetchTicker(): Promise<TickerItem[]> {
  // TODO: swap → fetch(`${BASE}/api/v1/web/ticker`).then(r => r.json())
  return MOCK_TICKER
}

export async function fetchCards(params: {
  signal?: Signal | 'ALL'
  sort?: 'change' | 'price' | 'volume'
  limit?: number
  offset?: number
}): Promise<CardsResponse> {
  // TODO: swap → fetch(`${BASE}/api/v1/web/cards?${new URLSearchParams({...})}`)
  const { signal = 'ALL', sort = 'change', limit = 50, offset = 0 } = params
  let cards = signal === 'ALL' ? MOCK_CARDS : MOCK_CARDS.filter(c => c.signal === signal)
  if (sort === 'price')  cards = [...cards].sort((a, b) => (b.tcg_price ?? 0) - (a.tcg_price ?? 0))
  if (sort === 'volume') cards = [...cards].sort((a, b) => (b.volume_24h ?? 0) - (a.volume_24h ?? 0))
  if (sort === 'change') cards = [...cards].sort((a, b) => Math.abs(b.price_delta_pct ?? 0) - Math.abs(a.price_delta_pct ?? 0))
  return { cards: cards.slice(offset, offset + limit), total: cards.length, limit, offset }
}

export async function fetchCard(assetId: string): Promise<CardDetail> {
  // TODO: swap → fetch(`${BASE}/api/v1/web/cards/${assetId}`).then(r => r.json())
  const found = MOCK_CARDS.find(c => c.asset_id === assetId)
  if (!found) throw new Error(`Card ${assetId} not found`)
  return {
    ...found,
    price_history: MOCK_PRICE_HISTORY,
    spread_pct: found.tcg_price && found.ebay_price
      ? +((found.tcg_price - found.ebay_price) / found.tcg_price * 100).toFixed(1)
      : null,
  }
}

export async function fetchAlerts(params: {
  filter?: 'ALL' | 'HIGH' | 'UNREAD'
  limit?: number
}): Promise<AlertsResponse> {
  // TODO: swap → fetch(`${BASE}/api/v1/web/alerts?${new URLSearchParams({...})}`)
  const readIds = getReadAlertIds()
  let alerts = MOCK_ALERTS
  if (params.filter === 'HIGH')   alerts = alerts.filter(a => a.severity === 'high')
  if (params.filter === 'UNREAD') alerts = alerts.filter(a => !readIds.has(a.id))
  return { alerts, total: alerts.length }
}
```

---

## Section 6 — New Backend Endpoints (`backend/app/api/routes/web.py`)

All public, no auth. Prefix `/api/v1/web`.  
DB dependency: `Depends(get_database)` from `backend.app.api.deps`.

### Schema notes (verified against live DB)

- Signal column is `label` (not `signal_label`) in both `asset_signals` and `asset_signal_history`
- All IDs are UUID — cast to `::text` when returning as JSON
- `assets` has direct columns: `name`, `set_name`, `card_number`, `language`, `variant`, `grade_score`, `category`, `game`; no price data
- Price data lives in `price_history`: columns `asset_id`, `source`, `price`, `captured_at`. Sources: `'pokemon_tcg_api'` and `'ebay_sold'`
- `asset_signals` has: `asset_id`, `label`, `price_delta_pct`, `liquidity_score`, `computed_at`. No `current_price`, no `ebay_price`
- `asset_signal_history` has same shape as `asset_signals` plus no `explanation` field. Transitions found via `LAG()` window function
- `scheduler_run_log.finished_at` (not `completed_at`); job_name is `'ingestion'`

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database

router = APIRouter(prefix="/api/v1/web", tags=["web"])


@router.get("/stats")
def web_stats(db: Session = Depends(get_database)):
    total = db.execute(text("SELECT COUNT(*) FROM assets")).scalar() or 0

    signal_rows = db.execute(text("""
        SELECT label, COUNT(*) AS cnt
        FROM asset_signals
        GROUP BY label
    """)).fetchall()
    counts: dict[str, int] = {r.label: r.cnt for r in signal_rows}
    for lbl in ("BREAKOUT", "MOVE", "WATCH", "IDLE", "INSUFFICIENT_DATA"):
        counts.setdefault(lbl, 0)

    last_ingest = db.execute(text("""
        SELECT finished_at FROM scheduler_run_log
        WHERE job_name = 'ingestion' AND status = 'success'
        ORDER BY finished_at DESC LIMIT 1
    """)).scalar()

    return {
        "total_assets": total,
        "signal_counts": counts,
        "last_ingest_utc": last_ingest.isoformat() if last_ingest else None,
        "next_ingest_utc": None,
        "sources_active": ["pokemon_tcg_api", "ebay_sold"],
    }


@router.get("/ticker")
def web_ticker(db: Session = Depends(get_database)):
    rows = db.execute(text("""
        SELECT
            a.id::text           AS asset_id,
            a.name,
            s.label              AS signal,
            s.price_delta_pct,
            ph.price             AS current_price
        FROM assets a
        JOIN asset_signals s ON s.asset_id = a.id
        LEFT JOIN LATERAL (
            SELECT price FROM price_history
            WHERE asset_id = a.id AND source = 'pokemon_tcg_api'
            ORDER BY captured_at DESC LIMIT 1
        ) ph ON TRUE
        WHERE s.label != 'INSUFFICIENT_DATA'
          AND s.price_delta_pct IS NOT NULL
        ORDER BY ABS(s.price_delta_pct) DESC
        LIMIT 10
    """)).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/cards")
def web_cards(
    signal: str = Query(default="ALL"),
    sort: str = Query(default="change"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
    db: Session = Depends(get_database),
):
    signal_filter = "" if signal == "ALL" else "AND s.label = :signal"
    order_map = {
        "change": "ABS(s.price_delta_pct) DESC NULLS LAST",
        "price":  "tcg_price DESC NULLS LAST",
        "volume": "volume_24h DESC NULLS LAST",
    }
    order = order_map.get(sort, order_map["change"])

    params: dict = {"limit": limit, "offset": offset}
    if signal != "ALL":
        params["signal"] = signal

    base = f"""
        FROM assets a
        JOIN asset_signals s ON s.asset_id = a.id
        LEFT JOIN LATERAL (
            SELECT price FROM price_history
            WHERE asset_id = a.id AND source = 'pokemon_tcg_api'
            ORDER BY captured_at DESC LIMIT 1
        ) tcg ON TRUE
        LEFT JOIN LATERAL (
            SELECT price FROM price_history
            WHERE asset_id = a.id AND source = 'ebay_sold'
            ORDER BY captured_at DESC LIMIT 1
        ) ebay ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS cnt FROM price_history
            WHERE asset_id = a.id AND source = 'ebay_sold'
              AND captured_at >= NOW() - INTERVAL '24 hours'
        ) vol ON TRUE
        WHERE 1=1 {signal_filter}
    """

    total = db.execute(text(f"SELECT COUNT(*) {base}"), params).scalar() or 0
    rows = db.execute(text(f"""
        SELECT
            a.id::text          AS asset_id,
            a.name,
            a.set_name,
            a.category          AS card_type,
            a.grade_score,
            s.label             AS signal,
            s.price_delta_pct,
            s.liquidity_score,
            tcg.price           AS tcg_price,
            ebay.price          AS ebay_price,
            vol.cnt             AS volume_24h,
            NULL::text          AS image_url
        {base}
        ORDER BY {order}
        LIMIT :limit OFFSET :offset
    """), params).fetchall()

    return {
        "cards": [dict(r._mapping) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/cards/{asset_id}")
def web_card_detail(asset_id: str, db: Session = Depends(get_database)):
    row = db.execute(text("""
        SELECT
            a.id::text          AS asset_id,
            a.name,
            a.set_name,
            a.category          AS card_type,
            s.label             AS signal,
            s.price_delta_pct,
            s.liquidity_score,
            tcg.price           AS tcg_price,
            ebay.price          AS ebay_price,
            NULL::text          AS image_url,
            CASE WHEN tcg.price > 0 AND ebay.price IS NOT NULL
                 THEN ROUND(((tcg.price - ebay.price) / tcg.price * 100)::numeric, 1)
                 ELSE NULL END  AS spread_pct
        FROM assets a
        JOIN asset_signals s ON s.asset_id = a.id
        LEFT JOIN LATERAL (
            SELECT price FROM price_history
            WHERE asset_id = a.id AND source = 'pokemon_tcg_api'
            ORDER BY captured_at DESC LIMIT 1
        ) tcg ON TRUE
        LEFT JOIN LATERAL (
            SELECT price FROM price_history
            WHERE asset_id = a.id AND source = 'ebay_sold'
            ORDER BY captured_at DESC LIMIT 1
        ) ebay ON TRUE
        WHERE a.id = :asset_id::uuid
    """), {"asset_id": asset_id}).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Card not found")

    history = db.execute(text("""
        SELECT
            DATE(captured_at)                                           AS date,
            AVG(price) FILTER (WHERE source = 'pokemon_tcg_api')       AS tcg_price,
            AVG(price) FILTER (WHERE source = 'ebay_sold')             AS ebay_price
        FROM price_history
        WHERE asset_id = :asset_id::uuid
          AND captured_at >= NOW() - INTERVAL '30 days'
        GROUP BY DATE(captured_at)
        ORDER BY date ASC
    """), {"asset_id": asset_id}).fetchall()

    return {
        **dict(row._mapping),
        "price_history": [
            {
                "date": str(h.date),
                "tcg_price": float(h.tcg_price) if h.tcg_price else None,
                "ebay_price": float(h.ebay_price) if h.ebay_price else None,
            }
            for h in history
        ],
    }


@router.get("/alerts")
def web_alerts(
    filter: str = Query(default="ALL"),
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_database),
):
    # Transitions: rows where label differs from the previous row for same asset
    # using LAG() window function over asset_signal_history
    extra = ""
    if filter == "HIGH":
        extra = "AND sub.current_signal = 'BREAKOUT'"

    rows = db.execute(text(f"""
        SELECT
            sub.id::text            AS id,
            sub.asset_id::text      AS asset_id,
            a.name                  AS card_name,
            sub.previous_signal,
            sub.current_signal,
            sub.price_delta_pct,
            sub.computed_at         AS created_at,
            CASE sub.current_signal
                WHEN 'BREAKOUT' THEN 'high'
                WHEN 'MOVE'     THEN 'medium'
                ELSE 'low'
            END                     AS severity
        FROM (
            SELECT
                id,
                asset_id,
                label       AS current_signal,
                LAG(label) OVER (PARTITION BY asset_id ORDER BY computed_at) AS previous_signal,
                price_delta_pct,
                computed_at
            FROM asset_signal_history
        ) sub
        JOIN assets a ON a.id = sub.asset_id
        WHERE sub.previous_signal IS DISTINCT FROM sub.current_signal
          AND sub.previous_signal IS NOT NULL
          {extra}
        ORDER BY sub.computed_at DESC
        LIMIT :limit
    """), {"limit": limit}).fetchall()

    alerts = []
    for r in rows:
        d = dict(r._mapping)
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        alerts.append(d)

    return {"alerts": alerts, "total": len(alerts)}
```

### Registration in `main.py`

```python
from backend.app.api.routes.web import router as web_router
# Add alongside other api_router.include_router(...) calls, or directly:
app.include_router(web_router)
```

---

## Section 7 — SPA Serving

### `site.py` (replace SSR routes with catch-all)

```python
from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path

router = APIRouter(include_in_schema=False)
_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

@router.get("/{full_path:path}")
async def serve_spa(full_path: str):
    index = _DIST / "index.html"
    if not index.exists():
        return JSONResponse({"error": "Frontend not built. Run: cd frontend && npm run build"}, status_code=503)
    return FileResponse(index)
```

### `main.py` additions (order matters)

```python
from fastapi.staticfiles import StaticFiles
from pathlib import Path

_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

# 1. Static assets (JS/CSS bundles) — BEFORE catch-all
if (_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="spa-assets")

# 2. API routers (existing + new web router) — BEFORE catch-all
# ... existing routers unchanged ...
app.include_router(web_router)

# 3. SPA catch-all — LAST
from backend.app.site import router as spa_router
app.include_router(spa_router)
```

---

## Section 8 — Vite Config

```typescript
// frontend/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8080', changeOrigin: true },
    },
  },
  build: { outDir: 'dist' },
})
```

`frontend/.env.local` (not committed):
```
VITE_API_BASE_URL=
```
Leave blank in dev (Vite proxy handles `/api/*`). Set to Railway URL in production.

---

## Section 9 — Utility Functions (`src/lib/utils.ts`)

```typescript
import type { Signal } from '../types/api'

const READ_KEY = 'fp_read_alerts'

export function getReadAlertIds(): Set<string> {
  try {
    const raw = localStorage.getItem(READ_KEY)
    return raw ? new Set(JSON.parse(raw)) : new Set()
  } catch { return new Set() }
}

export function markAlertRead(id: string): void {
  const ids = getReadAlertIds()
  ids.add(id)
  localStorage.setItem(READ_KEY, JSON.stringify([...ids]))
}

export function markAllAlertsRead(ids: string[]): void {
  localStorage.setItem(READ_KEY, JSON.stringify(ids))
}

export function typeToColor(cardType: string | null): string {
  const map: Record<string, string> = {
    Fire: '#ff6b35', Water: '#3b82f6', Grass: '#22c55e',
    Electric: '#ffcc00', Psychic: '#a855f7', Fighting: '#c2410c',
    Dark: '#4a0080', Dragon: '#1d4ed8', Steel: '#94a3b8',
    Fairy: '#ec4899', Normal: '#78716c', Colorless: '#87ceeb',
  }
  return map[cardType ?? ''] ?? '#6b7280'
}

export function relativeTime(isoString: string): string {
  const diff = Date.now() - new Date(isoString).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

export function signalToMeta(signal: Signal): {
  label: string; badgeClass: string; color: string; rowGlow: string
} {
  switch (signal) {
    case 'BREAKOUT': return { label: '▲ Breakout', badgeClass: 'badge-breakout', color: 'var(--breakout)', rowGlow: 'rgba(34,197,94,0.05)' }
    case 'MOVE':     return { label: '◆ Move',     badgeClass: 'badge-move',     color: 'var(--move)',     rowGlow: 'rgba(245,158,11,0.05)' }
    case 'WATCH':    return { label: '◆ Watch',    badgeClass: 'badge-watch',    color: 'var(--watch)',    rowGlow: 'rgba(251,146,60,0.05)' }
    case 'IDLE':     return { label: '— Idle',     badgeClass: 'badge-idle',     color: 'var(--idle)',     rowGlow: 'transparent' }
    case 'INSUFFICIENT_DATA': return { label: '· · ·', badgeClass: 'badge-nodata', color: 'var(--nodata)', rowGlow: 'transparent' }
  }
}
```

---

## Section 10 — Pages Summary

### LandingPage (`/`)
- Minimal header: logo + nav links + CTA
- TickerBar (data from `fetchTicker()`)
- Hero: 2-col grid. Left: headline "TCG Price / Intelligence / Platform" (gold on "Intelligence") + live pill badge + 4 stats from `fetchStats()` + two CTAs. Right: 3 floating `CardArt` with `.float` `.float-2` `.float-3`
- Feature section: 4 cards (Dual-source Data, Signal Engine, Discord Alerts, Price History)
- Footer: game badges (Pokémon live · Yu-Gi-Oh coming soon)

### DashboardPage (`/market`)
- NavBar + TickerBar
- 4 stat tiles: total assets, BREAKOUT count, MOVE count, WATCH count (from `fetchStats()`)
- Filter pills: All / ▲ Breakout / ◆ Move / ◆ Watch / — Idle
- Sort buttons: Change / Price / Volume
- Card grid `repeat(auto-fill, minmax(330px, 1fr))`. Each card: `CardArt sm` + name + set + `SignalBadge` + TCG price + eBay price + delta% + `Sparkline` + volume. Click → `/market/:asset_id`
- Loading: 6 skeleton cards; Empty: "No cards match this filter"

### CardDetailPage (`/market/:assetId`)
- NavBar + back button
- 2-col: left (280px) = `CardArt lg` (`.holo .float`) + name/set + info table + action buttons. Right = price tiles (TCG / eBay / Spread) + 24h change + area chart (`price_history`) + signal analysis box
- Area chart: SVG, y-axis price labels, area gradient fill, dot per data point
- Signal box: left-border colored by signal, text describing what the signal means

### AlertsPage (`/alerts`)
- NavBar
- Header: title + unread count (from localStorage comparison) + "Mark all read" button
- Discord status bar: green pulse dot + "Discord Connected" + stat chips
- Filter tabs: All / Unread / High Priority
- Alert list in `.surface`. Each row: unread dot + icon + card name + transition text (`IDLE → BREAKOUT`) + relative timestamp. Unread = colored left border by severity
- Click row → `markAlertRead(id)`, re-render
- "Mark all read" → `markAllAlertsRead(allIds)`, re-render

---

## Section 11 — Component Contracts

| Component | Props | Notes |
|---|---|---|
| `SignalBadge` | `signal: Signal` | Uses `signalToMeta()`. Never inline badge logic in pages. |
| `CardArt` | `color: string, name: string, type: string \| null, rarity: Rarity \| null, size: 'sm'\|'md'\|'lg'` | SVG illustration. `color` from `typeToColor`. Apply `.holo` on detail page. |
| `Sparkline` | `data: number[], width?, height?, color?` | SVG. Up trend → `var(--breakout)`, down → `#ef4444`. Area fill + end dot. |
| `TickerBar` | `items: TickerItem[]` | Duplicates array for seamless loop. |
| `NavBar` | — | Alerts link shows red dot if any unread (localStorage check). |

---

## Section 12 — Done Checklist

- [ ] `cd frontend && npm run dev` — all 4 pages render with mock data, no TS errors, no console errors
- [ ] All signal labels show as BREAKOUT / MOVE / WATCH / IDLE / `· · ·` — never BUY / SELL
- [ ] `INSUFFICIENT_DATA` badge uses dashed border, visually distinct from IDLE
- [ ] Filter tabs on dashboard include all 5 real signal labels (or at least BREAKOUT/MOVE/WATCH/IDLE with ALL)
- [ ] Alert rows show "IDLE → BREAKOUT" transition text
- [ ] Mark read / mark all read persists across page refresh (localStorage)
- [ ] `curl http://localhost:8080/api/v1/web/stats` returns valid JSON
- [ ] `curl http://localhost:8080/api/v1/web/ticker` returns array
- [ ] `curl http://localhost:8080/api/v1/web/cards` returns `{cards, total, limit, offset}`
- [ ] `curl http://localhost:8080/api/v1/web/cards/<uuid>` returns card + price_history
- [ ] `curl http://localhost:8080/api/v1/web/alerts` returns `{alerts, total}`
- [ ] `cd frontend && npm run build` — produces `dist/` without errors
- [ ] Full stack: built SPA served by FastAPI; direct URL `/market/<id>` doesn't 404
- [ ] No hardcoded colors in component files — all via CSS vars or `typeToColor()`
- [ ] No component imports directly from `mockData.ts` — all data flows through `api.ts`

---

## Schema Reference (verified 2026-04-22)

| Table | Key columns |
|---|---|
| `assets` | `id` (uuid), `name`, `set_name`, `category`, `game`, `grade_score`, `external_id` |
| `asset_signals` | `id` (uuid), `asset_id` (uuid), `label`, `price_delta_pct`, `liquidity_score`, `computed_at` |
| `asset_signal_history` | `id` (uuid), `asset_id` (uuid), `label`, `price_delta_pct`, `liquidity_score`, `computed_at` |
| `price_history` | `id` (uuid), `asset_id` (uuid), `source` ('pokemon_tcg_api'\|'ebay_sold'), `price`, `captured_at` |
| `scheduler_run_log` | `id` (int), `job_name`, `started_at`, `finished_at`, `status`, `records_written` |
