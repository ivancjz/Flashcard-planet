# Flashcard Planet Frontend + Web API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Vite + React + TypeScript SPA that replaces the existing SSR frontend, backed by five new public FastAPI endpoints under `/api/v1/web/`.

**Architecture:** SPA-first with typed mock adapter — all four pages ship against `mockData.ts` first, then each `api.ts` function is swapped to a real fetch once the backend endpoint passes its curl test. FastAPI serves the built `frontend/dist/` as static files; a catch-all route in `site.py` serves `index.html` for all non-API paths.

**Tech Stack:** Vite 5, React 18, TypeScript, React Router v6, plain CSS (no UI library), FastAPI, SQLAlchemy (raw `text()` queries), PostgreSQL.

---

## File Map

**Create (frontend):**
- `frontend/` — Vite scaffold
- `frontend/vite.config.ts`
- `frontend/.env.local`
- `frontend/src/types/api.ts` — all TypeScript types
- `frontend/src/lib/mockData.ts` — typed mock data
- `frontend/src/lib/utils.ts` — helpers: typeToColor, relativeTime, signalToMeta, localStorage
- `frontend/src/api/api.ts` — one function per endpoint, starts returning mocks
- `frontend/src/styles/theme.css` — CSS custom properties + utility classes
- `frontend/src/components/SignalBadge.tsx`
- `frontend/src/components/Sparkline.tsx`
- `frontend/src/components/CardArt.tsx`
- `frontend/src/components/TickerBar.tsx`
- `frontend/src/components/NavBar.tsx`
- `frontend/src/pages/LandingPage.tsx`
- `frontend/src/pages/DashboardPage.tsx`
- `frontend/src/pages/CardDetailPage.tsx`
- `frontend/src/pages/AlertsPage.tsx`
- `frontend/src/main.tsx` — BrowserRouter + Routes

**Create (backend):**
- `backend/app/api/routes/web.py` — five public endpoints
- `tests/test_web_routes.py` — integration tests

**Modify (backend):**
- `backend/app/api/router.py` — register web router
- `backend/app/main.py` — mount `frontend/dist/assets`, register web router before catch-all
- `backend/app/site.py` — strip SSR, add SPA catch-all

---

## Phase 1 — Frontend Foundation

### Task 1: Scaffold Vite + React + TypeScript

**Files:**
- Create: `frontend/` (Vite project)
- Create: `frontend/vite.config.ts`
- Create: `frontend/.env.local`

- [ ] **Step 1: Scaffold project**

```bash
cd c:/Flashcard-planet
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install react-router-dom
```

- [ ] **Step 2: Replace `vite.config.ts`**

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

- [ ] **Step 3: Create `.env.local`**

```
# frontend/.env.local
VITE_API_BASE_URL=
```

- [ ] **Step 4: Verify scaffold runs**

```bash
cd frontend && npm run dev
```

Expected: Vite dev server starts on `http://localhost:5173`, browser shows default Vite+React page. Ctrl+C to stop.

- [ ] **Step 5: Commit**

```bash
cd c:/Flashcard-planet
git add frontend/
git commit -m "feat(frontend): scaffold Vite + React + TS with react-router-dom"
```

---

### Task 2: Types, mock data, utils, API adapter

**Files:**
- Create: `frontend/src/types/api.ts`
- Create: `frontend/src/lib/mockData.ts`
- Create: `frontend/src/lib/utils.ts`
- Create: `frontend/src/api/api.ts`

- [ ] **Step 1: Write `src/types/api.ts`**

```typescript
// frontend/src/types/api.ts
export type Signal = 'BREAKOUT' | 'MOVE' | 'WATCH' | 'IDLE' | 'INSUFFICIENT_DATA'
export type Rarity = 'common' | 'uncommon' | 'rare' | 'holo' | 'ultra' | 'secret'

export interface MarketStats {
  total_assets: number
  signal_counts: Record<Signal, number>
  last_ingest_utc: string | null
  next_ingest_utc: string | null
  sources_active: string[]
}

export interface TickerItem {
  asset_id: string
  name: string
  price_delta_pct: number
  signal: Signal
  current_price: number | null
}

export interface CardSummary {
  asset_id: string
  name: string
  set_name: string | null
  rarity: Rarity | null
  card_type: string | null
  tcg_price: number | null
  ebay_price: number | null
  signal: Signal
  price_delta_pct: number | null
  liquidity_score: number | null
  volume_24h: number | null
  image_url: string | null
}

export interface PricePoint {
  date: string
  tcg_price: number | null
  ebay_price: number | null
}

export interface CardDetail extends CardSummary {
  price_history: PricePoint[]
  spread_pct: number | null
}

export interface AlertEvent {
  id: string
  asset_id: string
  card_name: string
  previous_signal: Signal | null
  current_signal: Signal
  price_delta_pct: number | null
  created_at: string
  severity: 'high' | 'medium' | 'low'
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

- [ ] **Step 2: Write `src/lib/mockData.ts`**

```typescript
// frontend/src/lib/mockData.ts
import type { MarketStats, TickerItem, CardSummary, PricePoint, AlertEvent } from '../types/api'

export const MOCK_STATS: MarketStats = {
  total_assets: 2897,
  signal_counts: { BREAKOUT: 45, MOVE: 296, WATCH: 96, IDLE: 121, INSUFFICIENT_DATA: 1965 },
  last_ingest_utc: '2026-04-19T09:14:07+00:00',
  next_ingest_utc: null,
  sources_active: ['pokemon_tcg_api', 'ebay_sold'],
}

export const MOCK_TICKER: TickerItem[] = [
  { asset_id: 'mock-0001', name: 'Charizard ex', price_delta_pct: 12.4, signal: 'BREAKOUT', current_price: 42.50 },
  { asset_id: 'mock-0002', name: 'Umbreon VMAX', price_delta_pct: 5.2, signal: 'WATCH', current_price: 89.99 },
  { asset_id: 'mock-0003', name: 'Rayquaza VMAX', price_delta_pct: -8.1, signal: 'MOVE', current_price: 55.00 },
  { asset_id: 'mock-0004', name: 'Pikachu VMAX', price_delta_pct: 18.7, signal: 'BREAKOUT', current_price: 32.00 },
  { asset_id: 'mock-0005', name: 'Giratina VSTAR', price_delta_pct: 2.1, signal: 'WATCH', current_price: 28.50 },
  { asset_id: 'mock-0006', name: 'Lugia VSTAR', price_delta_pct: -0.5, signal: 'IDLE', current_price: 35.00 },
]

export const MOCK_CARDS: CardSummary[] = [
  { asset_id: 'mock-0001', name: 'Charizard ex', set_name: 'Obsidian Flames', rarity: 'ultra', card_type: 'Fire', tcg_price: 42.50, ebay_price: 38.00, signal: 'BREAKOUT', price_delta_pct: 12.4, liquidity_score: 98, volume_24h: 847, image_url: null },
  { asset_id: 'mock-0002', name: 'Umbreon VMAX', set_name: 'Evolving Skies', rarity: 'secret', card_type: 'Dark', tcg_price: 89.99, ebay_price: 95.00, signal: 'WATCH', price_delta_pct: 5.2, liquidity_score: 72, volume_24h: 312, image_url: null },
  { asset_id: 'mock-0003', name: 'Rayquaza VMAX', set_name: 'Evolving Skies', rarity: 'ultra', card_type: 'Dragon', tcg_price: 55.00, ebay_price: 48.00, signal: 'MOVE', price_delta_pct: -8.1, liquidity_score: 81, volume_24h: 521, image_url: null },
  { asset_id: 'mock-0004', name: 'Pikachu VMAX', set_name: 'Hidden Fates', rarity: 'ultra', card_type: 'Electric', tcg_price: 32.00, ebay_price: 29.00, signal: 'BREAKOUT', price_delta_pct: 18.7, liquidity_score: 95, volume_24h: 1203, image_url: null },
  { asset_id: 'mock-0005', name: 'Giratina VSTAR', set_name: 'Lost Origin', rarity: 'holo', card_type: 'Dragon', tcg_price: 28.50, ebay_price: 31.00, signal: 'WATCH', price_delta_pct: 2.1, liquidity_score: 60, volume_24h: 444, image_url: null },
  { asset_id: 'mock-0006', name: 'Lugia VSTAR', set_name: 'Silver Tempest', rarity: 'ultra', card_type: 'Colorless', tcg_price: 35.00, ebay_price: 33.00, signal: 'IDLE', price_delta_pct: -0.5, liquidity_score: 44, volume_24h: 267, image_url: null },
  { asset_id: 'mock-0007', name: 'Mewtwo V-UNION', set_name: 'Celebrations', rarity: 'rare', card_type: 'Psychic', tcg_price: null, ebay_price: null, signal: 'INSUFFICIENT_DATA', price_delta_pct: null, liquidity_score: null, volume_24h: null, image_url: null },
]

export const MOCK_PRICE_HISTORY: PricePoint[] = Array.from({ length: 14 }, (_, i) => {
  const date = new Date('2026-04-05')
  date.setDate(date.getDate() + i)
  const base = 38 + Math.sin(i * 0.6) * 4
  return {
    date: date.toISOString().slice(0, 10),
    tcg_price: +(base + 4).toFixed(2),
    ebay_price: +(base).toFixed(2),
  }
})

export const MOCK_ALERTS: AlertEvent[] = [
  { id: 'alert-0001', asset_id: 'mock-0001', card_name: 'Charizard ex', previous_signal: 'WATCH', current_signal: 'BREAKOUT', price_delta_pct: 12.4, created_at: new Date(Date.now() - 3 * 60000).toISOString(), severity: 'high' },
  { id: 'alert-0002', asset_id: 'mock-0003', card_name: 'Rayquaza VMAX', previous_signal: 'IDLE', current_signal: 'MOVE', price_delta_pct: -8.1, created_at: new Date(Date.now() - 47 * 60000).toISOString(), severity: 'medium' },
  { id: 'alert-0003', asset_id: 'mock-0005', card_name: 'Giratina VSTAR', previous_signal: 'IDLE', current_signal: 'WATCH', price_delta_pct: 2.1, created_at: new Date(Date.now() - 3 * 3600000).toISOString(), severity: 'low' },
  { id: 'alert-0004', asset_id: 'mock-0004', card_name: 'Pikachu VMAX', previous_signal: 'MOVE', current_signal: 'BREAKOUT', price_delta_pct: 18.7, created_at: new Date(Date.now() - 26 * 3600000).toISOString(), severity: 'high' },
]
```

- [ ] **Step 3: Write `src/lib/utils.ts`**

```typescript
// frontend/src/lib/utils.ts
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

export function signalToMeta(signal: Signal): { label: string; badgeClass: string; color: string; rowGlow: string } {
  switch (signal) {
    case 'BREAKOUT':         return { label: '▲ Breakout', badgeClass: 'badge-breakout', color: 'var(--breakout)', rowGlow: 'rgba(34,197,94,0.05)' }
    case 'MOVE':             return { label: '◆ Move',     badgeClass: 'badge-move',     color: 'var(--move)',     rowGlow: 'rgba(245,158,11,0.05)' }
    case 'WATCH':            return { label: '◆ Watch',    badgeClass: 'badge-watch',    color: 'var(--watch)',    rowGlow: 'rgba(251,146,60,0.05)' }
    case 'IDLE':             return { label: '— Idle',     badgeClass: 'badge-idle',     color: 'var(--idle)',     rowGlow: 'transparent' }
    case 'INSUFFICIENT_DATA': return { label: '· · ·',    badgeClass: 'badge-nodata',   color: 'var(--nodata)',   rowGlow: 'transparent' }
  }
}
```

- [ ] **Step 4: Write `src/api/api.ts`**

```typescript
// frontend/src/api/api.ts
import type { MarketStats, TickerItem, CardsResponse, CardDetail, AlertsResponse, Signal } from '../types/api'
import { MOCK_STATS, MOCK_TICKER, MOCK_CARDS, MOCK_PRICE_HISTORY, MOCK_ALERTS } from '../lib/mockData'
import { getReadAlertIds } from '../lib/utils'

const BASE = import.meta.env.VITE_API_BASE_URL ?? ''

export async function fetchStats(): Promise<MarketStats> {
  // TODO: swap → const res = await fetch(`${BASE}/api/v1/web/stats`); return res.json()
  return MOCK_STATS
}

export async function fetchTicker(): Promise<TickerItem[]> {
  // TODO: swap → const res = await fetch(`${BASE}/api/v1/web/ticker`); return res.json()
  return MOCK_TICKER
}

export async function fetchCards(params: {
  signal?: Signal | 'ALL'
  sort?: 'change' | 'price' | 'volume'
  limit?: number
  offset?: number
}): Promise<CardsResponse> {
  // TODO: swap → const qs = new URLSearchParams({...}); return fetch(`${BASE}/api/v1/web/cards?${qs}`).then(r => r.json())
  const { signal = 'ALL', sort = 'change', limit = 50, offset = 0 } = params
  let cards = signal === 'ALL' ? MOCK_CARDS : MOCK_CARDS.filter(c => c.signal === signal)
  if (sort === 'price')  cards = [...cards].sort((a, b) => (b.tcg_price ?? 0) - (a.tcg_price ?? 0))
  if (sort === 'volume') cards = [...cards].sort((a, b) => (b.volume_24h ?? 0) - (a.volume_24h ?? 0))
  if (sort === 'change') cards = [...cards].sort((a, b) => Math.abs(b.price_delta_pct ?? 0) - Math.abs(a.price_delta_pct ?? 0))
  return { cards: cards.slice(offset, offset + limit), total: cards.length, limit, offset }
}

export async function fetchCard(assetId: string): Promise<CardDetail> {
  // TODO: swap → return fetch(`${BASE}/api/v1/web/cards/${assetId}`).then(r => r.json())
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
  // TODO: swap → const qs = new URLSearchParams({...}); return fetch(`${BASE}/api/v1/web/alerts?${qs}`).then(r => r.json())
  const readIds = getReadAlertIds()
  let alerts = MOCK_ALERTS
  if (params.filter === 'HIGH')   alerts = alerts.filter(a => a.severity === 'high')
  if (params.filter === 'UNREAD') alerts = alerts.filter(a => !readIds.has(a.id))
  return { alerts, total: alerts.length }
}
```

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors. If errors appear, fix them before continuing.

- [ ] **Step 6: Commit**

```bash
cd c:/Flashcard-planet
git add frontend/src/
git commit -m "feat(frontend): types, mock data, api adapter, utils"
```

---

### Task 3: Design tokens + app shell

**Files:**
- Create: `frontend/src/styles/theme.css`
- Modify: `frontend/src/main.tsx`
- Delete: `frontend/src/App.tsx`, `frontend/src/App.css`, `frontend/src/index.css`

- [ ] **Step 1: Write `src/styles/theme.css`** — paste the full CSS from the design spec (Section 4 of `docs/superpowers/specs/2026-04-22-frontend-design.md`). It includes all `:root` custom properties, utility classes (`.btn`, `.nav`, `.badge-*`, `.skeleton`, `.ticker-bar`, `.surface`, `.page-content`, animations).

- [ ] **Step 2: Replace `src/main.tsx` with app shell**

```tsx
// frontend/src/main.tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './styles/theme.css'

function Placeholder({ name }: { name: string }) {
  return (
    <div style={{ padding: 40, color: 'var(--text-primary)' }}>
      <h1 style={{ fontFamily: 'var(--font-display)' }}>{name}</h1>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Placeholder name="LandingPage" />} />
        <Route path="/market" element={<Placeholder name="DashboardPage" />} />
        <Route path="/market/:assetId" element={<Placeholder name="CardDetailPage" />} />
        <Route path="/alerts" element={<Placeholder name="AlertsPage" />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>
)
```

- [ ] **Step 3: Delete Vite boilerplate**

```bash
cd frontend && rm -f src/App.tsx src/App.css src/index.css src/assets/react.svg public/vite.svg
```

- [ ] **Step 4: Verify dark background**

```bash
cd frontend && npm run dev
```

Expected: page shows dark (`#0c0c10`) background, text "LandingPage" in white. No console errors.

- [ ] **Step 5: Commit**

```bash
cd c:/Flashcard-planet
git add frontend/
git commit -m "feat(frontend): design tokens + app shell with placeholder routes"
```

---

## Phase 2 — Components

### Task 4: SignalBadge + Sparkline

**Files:**
- Create: `frontend/src/components/SignalBadge.tsx`
- Create: `frontend/src/components/Sparkline.tsx`

- [ ] **Step 1: Write `SignalBadge.tsx`**

```tsx
// frontend/src/components/SignalBadge.tsx
import { signalToMeta } from '../lib/utils'
import type { Signal } from '../types/api'

export default function SignalBadge({ signal }: { signal: Signal }) {
  const { label, badgeClass } = signalToMeta(signal)
  return <span className={`badge ${badgeClass}`}>{label}</span>
}
```

- [ ] **Step 2: Write `Sparkline.tsx`**

```tsx
// frontend/src/components/Sparkline.tsx
interface SparklineProps {
  data: number[]
  width?: number
  height?: number
  color?: string
}

export default function Sparkline({ data, width = 80, height = 32, color }: SparklineProps) {
  if (data.length < 2) return <svg width={width} height={height} />

  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1

  const xStep = width / (data.length - 1)
  const yOf = (v: number) => height - ((v - min) / range) * (height - 4) - 2
  const pts = data.map((v, i) => `${i * xStep},${yOf(v)}`).join(' ')
  const areaPath = `M 0,${height} L ${pts.split(' ').join(' L ')} L ${(data.length - 1) * xStep},${height} Z`

  const trend = data[data.length - 1] >= data[0]
  const stroke = color ?? (trend ? 'var(--breakout)' : '#ef4444')
  const lastX = (data.length - 1) * xStep
  const lastY = yOf(data[data.length - 1])

  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      <defs>
        <linearGradient id={`sg-${data.length}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.3" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#sg-${data.length})`} />
      <polyline points={pts} fill="none" stroke={stroke} strokeWidth="1.5" />
      <circle cx={lastX} cy={lastY} r={2.5} fill={stroke} />
    </svg>
  )
}
```

- [ ] **Step 3: Quick smoke — add to placeholder route temporarily**

In `main.tsx` import `SignalBadge` and add `<SignalBadge signal="BREAKOUT" />` inside the LandingPage placeholder. Run `npm run dev` and confirm a green badge appears. Remove the temporary import after.

- [ ] **Step 4: Commit**

```bash
cd c:/Flashcard-planet
git add frontend/src/components/
git commit -m "feat(frontend): SignalBadge + Sparkline components"
```

---

### Task 5: CardArt + TickerBar

**Files:**
- Create: `frontend/src/components/CardArt.tsx`
- Create: `frontend/src/components/TickerBar.tsx`

- [ ] **Step 1: Write `CardArt.tsx`**

```tsx
// frontend/src/components/CardArt.tsx
import { typeToColor } from '../lib/utils'
import type { Rarity } from '../types/api'

const SIZE = { sm: { w: 120, h: 168, font: 10 }, md: { w: 180, h: 252, font: 13 }, lg: { w: 240, h: 336, font: 16 } }

interface CardArtProps {
  name: string
  type: string | null
  rarity: Rarity | null
  size?: 'sm' | 'md' | 'lg'
}

const RARITY_DOTS: Record<string, number> = { secret: 3, ultra: 2, holo: 1 }

export default function CardArt({ name, type, rarity, size = 'md' }: CardArtProps) {
  const color = typeToColor(type)
  const { w, h, font } = SIZE[size]
  const dots = RARITY_DOTS[rarity ?? ''] ?? 0

  return (
    <svg
      width={w} height={h}
      viewBox={`0 0 ${w} ${h}`}
      style={{ borderRadius: 8, display: 'block', flexShrink: 0 }}
    >
      <defs>
        <linearGradient id={`card-${name}-bg`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.9" />
          <stop offset="100%" stopColor="#0c0c10" stopOpacity="0.95" />
        </linearGradient>
        <radialGradient id={`card-${name}-glow`} cx="50%" cy="40%" r="55%">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor="transparent" stopOpacity="0" />
        </radialGradient>
      </defs>
      {/* Card background */}
      <rect width={w} height={h} fill={`url(#card-${name}-bg)`} rx={8} />
      <rect width={w} height={h} fill={`url(#card-${name}-glow)`} rx={8} />
      {/* Border */}
      <rect width={w} height={h} fill="none" stroke={color} strokeOpacity="0.4" strokeWidth="1" rx={8} />
      {/* Creature silhouette — abstract circle cluster */}
      <circle cx={w * 0.5} cy={h * 0.38} r={w * 0.22} fill={color} fillOpacity="0.15" />
      <circle cx={w * 0.5} cy={h * 0.35} r={w * 0.14} fill={color} fillOpacity="0.25" />
      <circle cx={w * 0.5} cy={h * 0.33} r={w * 0.07} fill={color} fillOpacity="0.5" />
      {/* Card name */}
      <text x={w / 2} y={h - 32} textAnchor="middle" fontSize={font} fontFamily="'Syne', sans-serif" fontWeight="700" fill="white" fillOpacity="0.9">
        {name.length > 18 ? name.slice(0, 17) + '…' : name}
      </text>
      {/* Type chip */}
      {type && (
        <>
          <rect x={w / 2 - 24} y={h - 22} width={48} height={14} rx={4} fill={color} fillOpacity="0.3" />
          <text x={w / 2} y={h - 12} textAnchor="middle" fontSize={8} fontFamily="'Space Mono', monospace" fill="white" fillOpacity="0.8">
            {type.toUpperCase()}
          </text>
        </>
      )}
      {/* Rarity dots */}
      {Array.from({ length: dots }, (_, i) => (
        <circle key={i} cx={w / 2 - (dots - 1) * 5 + i * 10} cy={h - 38} r={2.5} fill={color} fillOpacity="0.8" />
      ))}
    </svg>
  )
}
```

- [ ] **Step 2: Write `TickerBar.tsx`**

```tsx
// frontend/src/components/TickerBar.tsx
import { signalToMeta } from '../lib/utils'
import type { TickerItem } from '../types/api'

export default function TickerBar({ items }: { items: TickerItem[] }) {
  const doubled = [...items, ...items]
  return (
    <div className="ticker-bar">
      <div className="ticker-inner">
        {doubled.map((item, i) => {
          const up = item.price_delta_pct >= 0
          return (
            <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-secondary)' }}>
              <span style={{ color: signalToMeta(item.signal).color, fontSize: 10 }}>●</span>
              <span style={{ fontFamily: 'var(--font-body)', fontWeight: 500 }}>{item.name}</span>
              <span className={up ? 'up' : 'down'}>{up ? '▲' : '▼'} {Math.abs(item.price_delta_pct).toFixed(1)}%</span>
            </span>
          )
        })}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
cd c:/Flashcard-planet
git add frontend/src/components/
git commit -m "feat(frontend): CardArt + TickerBar components"
```

---

### Task 6: NavBar

**Files:**
- Create: `frontend/src/components/NavBar.tsx`

- [ ] **Step 1: Write `NavBar.tsx`**

```tsx
// frontend/src/components/NavBar.tsx
import { useNavigate, useLocation } from 'react-router-dom'
import { getReadAlertIds } from '../lib/utils'
import { MOCK_ALERTS } from '../lib/mockData'

export default function NavBar() {
  const nav = useNavigate()
  const { pathname } = useLocation()
  const readIds = getReadAlertIds()
  const hasUnread = MOCK_ALERTS.some(a => !readIds.has(a.id))

  const link = (path: string, label: string, extra?: React.ReactNode) => (
    <span
      className={`nav-link${pathname === path || pathname.startsWith(path + '/') ? ' active' : ''}`}
      onClick={() => nav(path)}
      style={{ position: 'relative' }}
    >
      {label}
      {extra}
    </span>
  )

  return (
    <nav className="nav">
      <div className="nav-logo" onClick={() => nav('/')}>
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <polygon points="10,1 12.9,7 19.5,7.6 14.8,11.8 16.2,18.2 10,15 3.8,18.2 5.2,11.8 0.5,7.6 7.1,7" fill="#f0b429" />
        </svg>
        Flashcard Planet
        <span className="nav-logo-sub">闪卡星球</span>
      </div>
      <div className="nav-links">
        {link('/market', 'Market')}
        {link('/alerts', 'Alerts',
          hasUnread && (
            <span style={{ position: 'absolute', top: 4, right: 4, width: 6, height: 6, borderRadius: '50%', background: '#ef4444' }} />
          )
        )}
      </div>
      <button className="btn btn-ghost btn-sm">Connect Discord</button>
    </nav>
  )
}
```

- [ ] **Step 2: Commit**

```bash
cd c:/Flashcard-planet
git add frontend/src/components/NavBar.tsx
git commit -m "feat(frontend): NavBar component"
```

---

## Phase 3 — Pages

### Task 7: LandingPage

**Files:**
- Create: `frontend/src/pages/LandingPage.tsx`

- [ ] **Step 1: Write `LandingPage.tsx`**

```tsx
// frontend/src/pages/LandingPage.tsx
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import TickerBar from '../components/TickerBar'
import CardArt from '../components/CardArt'
import { fetchStats, fetchTicker } from '../api/api'
import type { MarketStats, TickerItem } from '../types/api'

const FEATURES = [
  { icon: '📊', title: 'Dual-source Data', desc: 'TCGPlayer market price + eBay sold listings, reconciled daily.' },
  { icon: '⚡', title: 'Signal Engine', desc: 'BREAKOUT / MOVE / WATCH / IDLE labels computed every ingest run.' },
  { icon: '🔔', title: 'Discord Alerts', desc: 'Price spike and signal change notifications straight to your server.' },
  { icon: '📈', title: 'Price History', desc: '30-day rolling price chart per card from both sources.' },
]

export default function LandingPage() {
  const nav = useNavigate()
  const [stats, setStats] = useState<MarketStats | null>(null)
  const [ticker, setTicker] = useState<TickerItem[]>([])

  useEffect(() => {
    fetchStats().then(setStats)
    fetchTicker().then(setTicker)
  }, [])

  return (
    <div style={{ minHeight: '100vh' }}>
      {/* Minimal header */}
      <nav className="nav">
        <div className="nav-logo">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <polygon points="10,1 12.9,7 19.5,7.6 14.8,11.8 16.2,18.2 10,15 3.8,18.2 5.2,11.8 0.5,7.6 7.1,7" fill="#f0b429" />
          </svg>
          Flashcard Planet
          <span className="nav-logo-sub">闪卡星球</span>
        </div>
        <div className="nav-links">
          <span className="nav-link" onClick={() => nav('/market')}>Market</span>
          <span className="nav-link" onClick={() => nav('/alerts')}>Alerts</span>
        </div>
        <button className="btn btn-ghost btn-sm">Connect Discord</button>
      </nav>

      <TickerBar items={ticker} />

      {/* Hero */}
      <div className="page-content" style={{ paddingTop: 60 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 48, alignItems: 'center' }}>
          {/* Left */}
          <div className="fade-up">
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 16 }}>
              ● Live · Pokemon TCG
            </div>
            <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 52, fontWeight: 800, lineHeight: 1.1, letterSpacing: '-0.03em', marginBottom: 24 }}>
              TCG Price<br />
              <span style={{ color: 'var(--gold)' }}>Intelligence</span><br />
              Platform
            </h1>
            <p style={{ fontSize: 16, color: 'var(--text-secondary)', lineHeight: 1.6, maxWidth: 460, marginBottom: 32 }}>
              Track Pokemon TCG card prices across TCGPlayer and eBay. Get signal alerts before the market moves.
            </p>

            {/* Stats row */}
            {stats && (
              <div style={{ display: 'flex', gap: 32, marginBottom: 40 }}>
                {[
                  { label: 'Cards tracked', value: stats.total_assets.toLocaleString() },
                  { label: 'Breakout signals', value: stats.signal_counts.BREAKOUT },
                  { label: 'Data sources', value: stats.sources_active.length },
                  { label: 'Ingest interval', value: '24h' },
                ].map(({ label, value }) => (
                  <div key={label}>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 700, color: 'var(--text-primary)' }}>{value}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{label}</div>
                  </div>
                ))}
              </div>
            )}

            <div style={{ display: 'flex', gap: 12 }}>
              <button className="btn btn-primary" onClick={() => nav('/market')}>View Market →</button>
              <button className="btn btn-ghost" onClick={() => nav('/alerts')}>Discord Alerts</button>
            </div>
          </div>

          {/* Right — floating cards */}
          <div style={{ position: 'relative', height: 340 }}>
            <div className="float" style={{ position: 'absolute', top: 0, left: 20 }}>
              <CardArt name="Charizard ex" type="Fire" rarity="ultra" size="md" />
            </div>
            <div className="float-2" style={{ position: 'absolute', top: 60, left: 130 }}>
              <CardArt name="Umbreon VMAX" type="Dark" rarity="secret" size="md" />
            </div>
            <div className="float-3" style={{ position: 'absolute', top: 30, left: 80, zIndex: -1, opacity: 0.6 }}>
              <CardArt name="Giratina VSTAR" type="Dragon" rarity="holo" size="sm" />
            </div>
          </div>
        </div>

        {/* Feature grid */}
        <div style={{ marginTop: 80 }}>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 700, marginBottom: 32, textAlign: 'center' }}>
            Built for serious collectors
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
            {FEATURES.map(f => (
              <div key={f.title} className="surface" style={{ padding: 24 }}>
                <div style={{ fontSize: 28, marginBottom: 12 }}>{f.icon}</div>
                <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 600, marginBottom: 8 }}>{f.title}</h3>
                <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6 }}>{f.desc}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Footer CTA */}
        <div style={{ marginTop: 80, textAlign: 'center' }}>
          <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginBottom: 24 }}>
            <span className="badge badge-breakout">Pokémon · Live</span>
            <span className="badge badge-idle">Yu-Gi-Oh · Coming soon</span>
            <span className="badge badge-idle">MTG · Coming soon</span>
          </div>
          <button className="btn btn-primary" style={{ fontSize: 15, padding: '12px 32px' }} onClick={() => nav('/market')}>
            Explore the Market
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Update routing in `main.tsx`** — import and use `LandingPage`:

```tsx
import LandingPage from './pages/LandingPage'
// Replace <Placeholder name="LandingPage" /> with <LandingPage />
```

- [ ] **Step 3: Verify in browser** — `npm run dev`, visit `http://localhost:5173`. Confirm hero layout, floating cards, stats row, feature grid all render. Ticker scrolls.

- [ ] **Step 4: Commit**

```bash
cd c:/Flashcard-planet
git add frontend/src/pages/LandingPage.tsx frontend/src/main.tsx
git commit -m "feat(frontend): LandingPage"
```

---

### Task 8: DashboardPage

**Files:**
- Create: `frontend/src/pages/DashboardPage.tsx`

- [ ] **Step 1: Write `DashboardPage.tsx`**

```tsx
// frontend/src/pages/DashboardPage.tsx
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import NavBar from '../components/NavBar'
import TickerBar from '../components/TickerBar'
import SignalBadge from '../components/SignalBadge'
import CardArt from '../components/CardArt'
import Sparkline from '../components/Sparkline'
import { fetchStats, fetchCards, fetchTicker } from '../api/api'
import { signalToMeta } from '../lib/utils'
import type { Signal, CardSummary, MarketStats, TickerItem } from '../types/api'

type SortKey = 'change' | 'price' | 'volume'
const FILTERS: Array<{ value: Signal | 'ALL'; label: string }> = [
  { value: 'ALL', label: 'All' },
  { value: 'BREAKOUT', label: '▲ Breakout' },
  { value: 'MOVE', label: '◆ Move' },
  { value: 'WATCH', label: '◆ Watch' },
  { value: 'IDLE', label: '— Idle' },
]

function SkeletonCard() {
  return (
    <div className="surface" style={{ padding: 16 }}>
      <div className="skeleton" style={{ height: 168, marginBottom: 12, borderRadius: 8 }} />
      <div className="skeleton" style={{ height: 14, width: '70%', marginBottom: 8 }} />
      <div className="skeleton" style={{ height: 12, width: '50%' }} />
    </div>
  )
}

export default function DashboardPage() {
  const nav = useNavigate()
  const [stats, setStats] = useState<MarketStats | null>(null)
  const [ticker, setTicker] = useState<TickerItem[]>([])
  const [cards, setCards] = useState<CardSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [signal, setSignal] = useState<Signal | 'ALL'>('ALL')
  const [sort, setSort] = useState<SortKey>('change')

  useEffect(() => { fetchStats().then(setStats); fetchTicker().then(setTicker) }, [])

  useEffect(() => {
    setLoading(true)
    fetchCards({ signal, sort }).then(r => { setCards(r.cards); setLoading(false) })
  }, [signal, sort])

  return (
    <div>
      <NavBar />
      <TickerBar items={ticker} />
      <div className="page-content">
        {/* Stat tiles */}
        {stats && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 28 }}>
            {([
              { label: 'Total assets', value: stats.total_assets },
              { label: 'Breakout', value: stats.signal_counts.BREAKOUT, color: 'var(--breakout)' },
              { label: 'Move', value: stats.signal_counts.MOVE, color: 'var(--move)' },
              { label: 'Watch', value: stats.signal_counts.WATCH, color: 'var(--watch)' },
            ] as const).map(tile => (
              <div key={tile.label} className="surface" style={{ padding: '16px 20px' }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 26, fontWeight: 700, color: ('color' in tile ? tile.color : 'var(--text-primary)') as string }}>
                  {tile.value}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>{tile.label}</div>
              </div>
            ))}
          </div>
        )}

        {/* Filters + sort */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <div style={{ display: 'flex', gap: 6 }}>
            {FILTERS.map(f => (
              <button
                key={f.value}
                className={`btn btn-ghost btn-sm${signal === f.value ? '' : ''}`}
                onClick={() => setSignal(f.value)}
                style={signal === f.value ? { background: 'var(--bg-elevated)', color: 'var(--text-primary)', borderColor: 'var(--border-strong)' } : {}}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            {(['change', 'price', 'volume'] as SortKey[]).map(s => (
              <button key={s} className="btn btn-ghost btn-sm" onClick={() => setSort(s)}
                style={sort === s ? { background: 'var(--bg-elevated)', color: 'var(--gold)', borderColor: 'var(--gold-dim)' } : {}}>
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* Card grid */}
        {loading ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(330px, 1fr))', gap: 16 }}>
            {Array.from({ length: 6 }, (_, i) => <SkeletonCard key={i} />)}
          </div>
        ) : cards.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 80, color: 'var(--text-muted)' }}>No cards match this filter</div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(330px, 1fr))', gap: 16 }}>
            {cards.map(card => {
              const meta = signalToMeta(card.signal)
              const sparkData = [30, 32, 31, 35, 34, 38, card.tcg_price ?? 35]
              const up = (card.price_delta_pct ?? 0) >= 0
              return (
                <div
                  key={card.asset_id}
                  className="surface"
                  onClick={() => nav(`/market/${card.asset_id}`)}
                  style={{
                    padding: 16, cursor: 'pointer', display: 'flex', gap: 12, alignItems: 'flex-start',
                    background: `linear-gradient(135deg, ${meta.rowGlow} 0%, var(--bg-surface) 60%)`,
                    borderLeft: `3px solid ${meta.color}`,
                    transition: 'transform 0.15s, box-shadow 0.15s',
                  }}
                  onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.transform = 'translateY(-2px)'; (e.currentTarget as HTMLDivElement).style.boxShadow = `0 8px 32px ${meta.color}20` }}
                  onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.transform = ''; (e.currentTarget as HTMLDivElement).style.boxShadow = '' }}
                >
                  <CardArt name={card.name} type={card.card_type} rarity={card.rarity} size="sm" />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
                      <div>
                        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 160 }}>{card.name}</div>
                        <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{card.set_name}</div>
                      </div>
                      <SignalBadge signal={card.signal} />
                    </div>
                    <div style={{ display: 'flex', gap: 16, marginTop: 10, marginBottom: 10 }}>
                      <div>
                        <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>TCG</div>
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-primary)' }}>{card.tcg_price != null ? `$${card.tcg_price.toFixed(2)}` : '—'}</div>
                      </div>
                      <div>
                        <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>eBay</div>
                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-primary)' }}>{card.ebay_price != null ? `$${card.ebay_price.toFixed(2)}` : '—'}</div>
                      </div>
                      <div>
                        <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>24h</div>
                        <div className={up ? 'up' : 'down'}>{card.price_delta_pct != null ? `${up ? '+' : ''}${card.price_delta_pct.toFixed(1)}%` : '—'}</div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Sparkline data={sparkData} width={80} height={28} />
                      <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{card.volume_24h != null ? `${card.volume_24h} sales` : ''}</div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Wire into `main.tsx`**

```tsx
import DashboardPage from './pages/DashboardPage'
// Replace <Placeholder name="DashboardPage" /> with <DashboardPage />
```

- [ ] **Step 3: Verify** — `npm run dev`, visit `/market`. Confirm stat tiles, filter pills, card grid with signal badges. Click a filter pill and confirm grid re-renders. Click a card and confirm navigation to `/market/mock-0001`.

- [ ] **Step 4: Commit**

```bash
cd c:/Flashcard-planet
git add frontend/src/pages/DashboardPage.tsx frontend/src/main.tsx
git commit -m "feat(frontend): DashboardPage with filter, sort, card grid"
```

---

### Task 9: CardDetailPage

**Files:**
- Create: `frontend/src/pages/CardDetailPage.tsx`

- [ ] **Step 1: Write `CardDetailPage.tsx`**

```tsx
// frontend/src/pages/CardDetailPage.tsx
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import NavBar from '../components/NavBar'
import CardArt from '../components/CardArt'
import SignalBadge from '../components/SignalBadge'
import { fetchCard } from '../api/api'
import { signalToMeta } from '../lib/utils'
import type { CardDetail, PricePoint } from '../types/api'

const SIGNAL_DESCRIPTION: Record<string, string> = {
  BREAKOUT: 'Price has jumped significantly above baseline. High sales volume confirms buyer demand. Consider acting before the market adjusts.',
  MOVE: 'Price is shifting directionally with above-average volume. Momentum is building — watch closely.',
  WATCH: 'Early signals of price movement detected. Not yet confirmed — monitor the next 24–48h.',
  IDLE: 'No significant price movement. Market is stable for this card.',
  INSUFFICIENT_DATA: 'Not enough recent sales data to compute a reliable signal.',
}

function AreaChart({ data }: { data: PricePoint[] }) {
  const W = 560, H = 160
  const PAD = { top: 12, right: 12, bottom: 28, left: 48 }
  const IW = W - PAD.left - PAD.right
  const IH = H - PAD.top - PAD.bottom

  const allPrices = data.flatMap(d => [d.tcg_price, d.ebay_price]).filter((v): v is number => v != null)
  if (allPrices.length === 0) return <div style={{ color: 'var(--text-muted)', padding: 20 }}>No price history available.</div>

  const minP = Math.min(...allPrices)
  const maxP = Math.max(...allPrices)
  const range = maxP - minP || 1
  const xOf = (i: number) => (i / Math.max(data.length - 1, 1)) * IW
  const yOf = (p: number) => IH - ((p - minP) / range) * IH

  const linePoints = (prices: (number | null)[]) =>
    prices.map((p, i) => p != null ? `${xOf(i)},${yOf(p)}` : null).filter(Boolean).join(' L ')

  const areaPath = (prices: (number | null)[]) => {
    const pts = prices.map((p, i) => p != null ? [xOf(i), yOf(p)] as [number, number] : null).filter((x): x is [number,number] => x != null)
    if (!pts.length) return ''
    return `M ${pts[0][0]},${IH} L ${pts.map(([x,y]) => `${x},${y}`).join(' L ')} L ${pts[pts.length-1][0]},${IH} Z`
  }

  const tcgPrices = data.map(d => d.tcg_price)
  const ebayPrices = data.map(d => d.ebay_price)
  const lastIdx = data.length - 1

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block' }}>
      <defs>
        <linearGradient id="tcg-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--gold)" stopOpacity="0.3" />
          <stop offset="100%" stopColor="var(--gold)" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="ebay-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--breakout)" stopOpacity="0.15" />
          <stop offset="100%" stopColor="var(--breakout)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <g transform={`translate(${PAD.left},${PAD.top})`}>
        {/* Y-axis labels */}
        {[minP, (minP + maxP) / 2, maxP].map((p, i) => (
          <text key={i} x={-6} y={yOf(p) + 4} textAnchor="end" fontSize={9} fontFamily="'Space Mono', monospace" fill="var(--text-muted)">
            ${p.toFixed(0)}
          </text>
        ))}
        {/* eBay area + line */}
        {areaPath(ebayPrices) && <path d={areaPath(ebayPrices)} fill="url(#ebay-area)" />}
        {linePoints(ebayPrices) && <path d={`M ${linePoints(ebayPrices)}`} fill="none" stroke="var(--breakout)" strokeWidth={1.5} strokeDasharray="4 2" opacity={0.7} />}
        {/* TCG area + line */}
        {areaPath(tcgPrices) && <path d={areaPath(tcgPrices)} fill="url(#tcg-area)" />}
        {linePoints(tcgPrices) && <path d={`M ${linePoints(tcgPrices)}`} fill="none" stroke="var(--gold)" strokeWidth={2} />}
        {/* End dots */}
        {tcgPrices[lastIdx] != null && <circle cx={xOf(lastIdx)} cy={yOf(tcgPrices[lastIdx]!)} r={4} fill="var(--gold)" stroke="var(--bg-base)" strokeWidth={2} />}
        {ebayPrices[lastIdx] != null && <circle cx={xOf(lastIdx)} cy={yOf(ebayPrices[lastIdx]!)} r={3} fill="var(--breakout)" stroke="var(--bg-base)" strokeWidth={1.5} />}
        {/* X-axis date labels */}
        {[0, Math.floor(data.length / 2), lastIdx].map(i => (
          <text key={i} x={xOf(i)} y={IH + 18} textAnchor="middle" fontSize={9} fontFamily="'Space Mono', monospace" fill="var(--text-muted)">
            {data[i]?.date?.slice(5)}
          </text>
        ))}
      </g>
    </svg>
  )
}

export default function CardDetailPage() {
  const { assetId } = useParams<{ assetId: string }>()
  const nav = useNavigate()
  const [card, setCard] = useState<CardDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!assetId) return
    setLoading(true)
    fetchCard(assetId)
      .then(setCard)
      .catch(() => setError('Card not found.'))
      .finally(() => setLoading(false))
  }, [assetId])

  if (loading) return (
    <div>
      <NavBar />
      <div className="page-content" style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 32 }}>
        <div className="skeleton" style={{ height: 336 }} />
        <div><div className="skeleton" style={{ height: 160, marginBottom: 16 }} /><div className="skeleton" style={{ height: 200 }} /></div>
      </div>
    </div>
  )

  if (error || !card) return (
    <div><NavBar /><div className="page-content" style={{ color: '#ef4444' }}>{error ?? 'Card not found.'}</div></div>
  )

  const meta = signalToMeta(card.signal)
  const up = (card.price_delta_pct ?? 0) >= 0

  return (
    <div>
      <NavBar />
      <div className="page-content">
        <button className="btn btn-ghost btn-sm" onClick={() => nav(-1)} style={{ marginBottom: 24 }}>← Back to Market</button>

        <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 32, alignItems: 'start' }}>
          {/* Left column */}
          <div>
            <div className="holo float" style={{ marginBottom: 20 }}>
              <CardArt name={card.name} type={card.card_type} rarity={card.rarity} size="lg" />
            </div>
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 20, fontWeight: 700, marginBottom: 4 }}>{card.name}</h2>
            <div style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>{card.set_name}</div>
            <table style={{ fontSize: 12, width: '100%', borderCollapse: 'collapse' }}>
              {[
                ['Signal', <SignalBadge signal={card.signal} />],
                ['Type', card.card_type ?? '—'],
                ['Rarity', card.rarity ?? '—'],
                ['Liquidity', card.liquidity_score != null ? `${card.liquidity_score}/100` : '—'],
              ].map(([label, value]) => (
                <tr key={String(label)} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                  <td style={{ padding: '8px 0', color: 'var(--text-muted)' }}>{label}</td>
                  <td style={{ padding: '8px 0', textAlign: 'right' }}>{value}</td>
                </tr>
              ))}
            </table>
            <div style={{ marginTop: 20, display: 'flex', flexDirection: 'column', gap: 10 }}>
              <button className="btn btn-primary" style={{ width: '100%', justifyContent: 'center' }}>Set Alert</button>
              <button className="btn btn-ghost" style={{ width: '100%', justifyContent: 'center' }}>Add to Watchlist</button>
            </div>
          </div>

          {/* Right column */}
          <div>
            {/* Price tiles */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 20 }}>
              {[
                { label: 'TCGPlayer', value: card.tcg_price != null ? `$${card.tcg_price.toFixed(2)}` : '—', color: 'var(--gold)' },
                { label: 'eBay sold', value: card.ebay_price != null ? `$${card.ebay_price.toFixed(2)}` : '—', color: 'var(--breakout)' },
                { label: 'Spread', value: card.spread_pct != null ? `${card.spread_pct.toFixed(1)}%` : '—', color: 'var(--text-secondary)' },
              ].map(tile => (
                <div key={tile.label} className="surface" style={{ padding: '16px 20px' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 6 }}>{tile.label}</div>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 700, color: tile.color }}>{tile.value}</div>
                </div>
              ))}
            </div>

            {/* 24h change row */}
            <div className="surface" style={{ padding: '12px 20px', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>24h change</span>
              <span className={up ? 'up' : 'down'} style={{ fontSize: 16, fontWeight: 700 }}>
                {card.price_delta_pct != null ? `${up ? '+' : ''}${card.price_delta_pct.toFixed(1)}%` : '—'}
              </span>
            </div>

            {/* Area chart */}
            <div className="surface" style={{ padding: 20, marginBottom: 20 }}>
              <div style={{ display: 'flex', gap: 16, marginBottom: 12 }}>
                <span style={{ fontSize: 12, color: 'var(--gold)' }}>— TCGPlayer</span>
                <span style={{ fontSize: 12, color: 'var(--breakout)' }}>-- eBay sold</span>
              </div>
              <AreaChart data={card.price_history} />
            </div>

            {/* Signal analysis */}
            <div className="surface" style={{ padding: 20, borderLeft: `4px solid ${meta.color}` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                <SignalBadge signal={card.signal} />
                <span style={{ fontSize: 13, fontWeight: 600, color: meta.color }}>Signal Analysis</span>
              </div>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
                {SIGNAL_DESCRIPTION[card.signal]}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Wire into `main.tsx`**

```tsx
import CardDetailPage from './pages/CardDetailPage'
// Replace <Placeholder name="CardDetailPage" /> with <CardDetailPage />
```

- [ ] **Step 3: Verify** — visit `/market`, click a card. Confirm 2-column layout, area chart renders (both gold TCG line and green eBay dashed line), signal analysis box has colored left border. Back button returns to `/market`.

- [ ] **Step 4: Commit**

```bash
cd c:/Flashcard-planet
git add frontend/src/pages/CardDetailPage.tsx frontend/src/main.tsx
git commit -m "feat(frontend): CardDetailPage with area chart + signal analysis"
```

---

### Task 10: AlertsPage + final routing

**Files:**
- Create: `frontend/src/pages/AlertsPage.tsx`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Write `AlertsPage.tsx`**

```tsx
// frontend/src/pages/AlertsPage.tsx
import { useEffect, useState, useCallback } from 'react'
import NavBar from '../components/NavBar'
import SignalBadge from '../components/SignalBadge'
import { fetchAlerts } from '../api/api'
import { getReadAlertIds, markAlertRead, markAllAlertsRead, relativeTime, signalToMeta } from '../lib/utils'
import type { AlertEvent } from '../types/api'

type Filter = 'ALL' | 'UNREAD' | 'HIGH'

const SEVERITY_COLOR: Record<string, string> = {
  high: 'var(--breakout)',
  medium: 'var(--move)',
  low: 'var(--watch)',
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertEvent[]>([])
  const [filter, setFilter] = useState<Filter>('ALL')
  const [readIds, setReadIds] = useState<Set<string>>(getReadAlertIds)

  const load = useCallback(() => {
    fetchAlerts({ filter }).then(r => setAlerts(r.alerts))
  }, [filter])

  useEffect(() => { load() }, [load])

  const handleRead = (id: string) => {
    markAlertRead(id)
    setReadIds(new Set([...readIds, id]))
  }

  const handleReadAll = () => {
    const ids = alerts.map(a => a.id)
    markAllAlertsRead(ids)
    setReadIds(new Set(ids))
  }

  const unreadCount = alerts.filter(a => !readIds.has(a.id)).length

  return (
    <div>
      <NavBar />
      <div className="page-content">
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <h1 className="page-title">Discord Alerts</h1>
              {unreadCount > 0 && (
                <span style={{ background: '#ef4444', color: 'white', fontSize: 11, fontFamily: 'var(--font-mono)', padding: '2px 8px', borderRadius: 10 }}>
                  {unreadCount} new
                </span>
              )}
            </div>
            <p className="page-subtitle">Signal change events</p>
          </div>
          {unreadCount > 0 && (
            <button className="btn btn-ghost btn-sm" onClick={handleReadAll}>Mark all read</button>
          )}
        </div>

        {/* Discord status bar */}
        <div className="surface" style={{ padding: '10px 16px', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 16 }}>
          <span className="pulse-dot" style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--breakout)', display: 'inline-block' }} />
          <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Discord Connected</span>
          <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>#price-alerts</span>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            {['Next ingest: 24h', 'Signal sweep: OK', 'eBay: active'].map(chip => (
              <span key={chip} style={{ fontSize: 11, background: 'var(--bg-elevated)', padding: '3px 10px', borderRadius: 4, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{chip}</span>
            ))}
          </div>
        </div>

        {/* Filter tabs */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
          {(['ALL', 'UNREAD', 'HIGH'] as Filter[]).map(f => (
            <button key={f} className="btn btn-ghost btn-sm" onClick={() => setFilter(f)}
              style={filter === f ? { background: 'var(--bg-elevated)', color: 'var(--text-primary)', borderColor: 'var(--border-strong)' } : {}}>
              {f === 'ALL' ? 'All' : f === 'UNREAD' ? 'Unread' : 'High Priority'}
            </button>
          ))}
        </div>

        {/* Alert list */}
        <div className="surface">
          {alerts.length === 0 && (
            <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-muted)' }}>No alerts match this filter.</div>
          )}
          {alerts.map((alert, i) => {
            const isRead = readIds.has(alert.id)
            const meta = signalToMeta(alert.current_signal)
            const prevMeta = alert.previous_signal ? signalToMeta(alert.previous_signal) : null
            return (
              <div
                key={alert.id}
                onClick={() => handleRead(alert.id)}
                style={{
                  padding: '14px 20px',
                  borderBottom: i < alerts.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                  display: 'flex', alignItems: 'center', gap: 14,
                  cursor: 'pointer',
                  borderLeft: isRead ? '3px solid transparent' : `3px solid ${SEVERITY_COLOR[alert.severity]}`,
                  background: isRead ? 'transparent' : `${SEVERITY_COLOR[alert.severity]}08`,
                  transition: 'background 0.15s',
                }}
              >
                {/* Unread dot */}
                <div style={{ width: 8, height: 8, borderRadius: '50%', flexShrink: 0, background: isRead ? 'transparent' : SEVERITY_COLOR[alert.severity] }} />

                {/* Icon */}
                <div style={{ fontSize: 18, flexShrink: 0 }}>
                  {alert.severity === 'high' ? '🔥' : alert.severity === 'medium' ? '📊' : '👁️'}
                </div>

                {/* Content */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <span style={{ fontWeight: 600, fontSize: 14 }}>{alert.card_name}</span>
                    <SignalBadge signal={alert.current_signal} />
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                    {prevMeta ? (
                      <>
                        <span style={{ color: 'var(--text-muted)' }}>{prevMeta.label}</span>
                        {' → '}
                        <span style={{ color: meta.color, fontWeight: 600 }}>{meta.label}</span>
                      </>
                    ) : (
                      <span style={{ color: meta.color }}>{meta.label}</span>
                    )}
                    {alert.price_delta_pct != null && (
                      <span style={{ marginLeft: 8 }} className={alert.price_delta_pct >= 0 ? 'up' : 'down'}>
                        {alert.price_delta_pct >= 0 ? '+' : ''}{alert.price_delta_pct.toFixed(1)}%
                      </span>
                    )}
                  </div>
                </div>

                {/* Timestamp */}
                <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
                  {relativeTime(alert.created_at)}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Final `main.tsx`** — replace all four placeholders with real pages:

```tsx
// frontend/src/main.tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './styles/theme.css'
import LandingPage from './pages/LandingPage'
import DashboardPage from './pages/DashboardPage'
import CardDetailPage from './pages/CardDetailPage'
import AlertsPage from './pages/AlertsPage'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/market" element={<DashboardPage />} />
        <Route path="/market/:assetId" element={<CardDetailPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>
)
```

- [ ] **Step 3: Commit**

```bash
cd c:/Flashcard-planet
git add frontend/src/pages/AlertsPage.tsx frontend/src/main.tsx
git commit -m "feat(frontend): AlertsPage + complete routing"
```

---

### Task 11: Frontend smoke test

- [ ] **Step 1: Run dev server and check all pages**

```bash
cd frontend && npm run dev
```

Visit each route and confirm:

| Route | Check |
|---|---|
| `/` | Dark hero, ticker scrolls, floating cards, stats numbers, feature grid |
| `/market` | Filter pills (All/Breakout/Move/Watch/Idle), sort buttons, card grid renders, signal badges use real labels |
| `/market/mock-0007` | Loads INSUFFICIENT_DATA card, badge is dashed `· · ·`, no BUY/SELL label anywhere |
| `/market/mock-0001` | 2-col layout, area chart with gold TCG line + green eBay dashed, signal analysis box |
| `/alerts` | Alert list, click row → left dot disappears (mark-read). Refresh → still read. "Mark all read" clears all dots. |

- [ ] **Step 2: TypeScript clean build**

```bash
cd frontend && npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 3: Commit**

```bash
cd c:/Flashcard-planet
git commit -m "chore: frontend smoke test passed — all 4 pages render with mock data"
```

---

## Phase 3 — Backend Endpoints

### Task 12: `web.py` — stats + ticker

**Files:**
- Create: `backend/app/api/routes/web.py`
- Create: `tests/test_web_routes.py`

- [ ] **Step 1: Write `tests/test_web_routes.py` (stats + ticker tests)**

```python
# tests/test_web_routes.py
from unittest import TestCase
from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.app.api.routes.web import router
from backend.app.api.deps import get_database


def _fake_db():
    yield MagicMock()


class WebStatsTests(TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_database] = _fake_db
        self.client = TestClient(app)

    def tearDown(self):
        pass

    def test_stats_returns_200_and_required_fields(self):
        with patch("backend.app.api.routes.web.text") as mock_text:
            # Make all db.execute().scalar() calls return 100
            # Make all db.execute().fetchall() calls return []
            mock_session = MagicMock()
            mock_session.execute.return_value.scalar.return_value = 100
            mock_session.execute.return_value.fetchall.return_value = []

            def override():
                yield mock_session

            from fastapi import FastAPI
            app2 = FastAPI()
            app2.include_router(router)
            app2.dependency_overrides[get_database] = override
            client2 = TestClient(app2)
            response = client2.get("/api/v1/web/stats")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_assets", data)
        self.assertIn("signal_counts", data)
        for label in ("BREAKOUT", "MOVE", "WATCH", "IDLE", "INSUFFICIENT_DATA"):
            self.assertIn(label, data["signal_counts"])
        self.assertIn("sources_active", data)

    def test_ticker_returns_200_and_list(self):
        mock_session = MagicMock()
        mock_session.execute.return_value.fetchall.return_value = []

        def override():
            yield mock_session

        app2 = FastAPI()
        app2.include_router(router)
        app2.dependency_overrides[get_database] = override
        client2 = TestClient(app2)
        response = client2.get("/api/v1/web/ticker")

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)
```

- [ ] **Step 2: Run tests — expect FAIL (module not found)**

```bash
cd c:/Flashcard-planet && python -m pytest tests/test_web_routes.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` because `web.py` doesn't exist yet.

- [ ] **Step 3: Create `backend/app/api/routes/web.py`** with stats + ticker endpoints:

```python
# backend/app/api/routes/web.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database

router = APIRouter(prefix="/api/v1/web", tags=["web"])


@router.get("/stats")
def web_stats(db: Session = Depends(get_database)):
    total = db.execute(text("SELECT COUNT(*) FROM assets")).scalar() or 0

    signal_rows = db.execute(text(
        "SELECT label, COUNT(*) AS cnt FROM asset_signals GROUP BY label"
    )).fetchall()
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
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd c:/Flashcard-planet && python -m pytest tests/test_web_routes.py::WebStatsTests -v
```

Expected: `test_stats_returns_200_and_required_fields` PASS, `test_ticker_returns_200_and_list` PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/web.py tests/test_web_routes.py
git commit -m "feat(backend): web.py stats + ticker endpoints with tests"
```

---

### Task 13: `web.py` — cards list + card detail

- [ ] **Step 1: Add tests to `tests/test_web_routes.py`**

```python
class WebCardsTests(TestCase):
    def _make_client(self, mock_session):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_database] = lambda: iter([mock_session])
        return TestClient(app)

    def test_cards_returns_pagination_shape(self):
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = 0
        mock_session.execute.return_value.fetchall.return_value = []
        client = self._make_client(mock_session)
        response = client.get("/api/v1/web/cards")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("cards", data)
        self.assertIn("total", data)
        self.assertIn("limit", data)
        self.assertIn("offset", data)
        self.assertIsInstance(data["cards"], list)

    def test_cards_accepts_signal_filter(self):
        mock_session = MagicMock()
        mock_session.execute.return_value.scalar.return_value = 0
        mock_session.execute.return_value.fetchall.return_value = []
        client = self._make_client(mock_session)
        response = client.get("/api/v1/web/cards?signal=BREAKOUT&sort=price&limit=10")
        self.assertEqual(response.status_code, 200)

    def test_card_detail_404_on_missing(self):
        mock_session = MagicMock()
        mock_session.execute.return_value.fetchone.return_value = None
        client = self._make_client(mock_session)
        response = client.get("/api/v1/web/cards/00000000-0000-0000-0000-000000000000")
        self.assertEqual(response.status_code, 404)
```

- [ ] **Step 2: Run — expect FAIL**

```bash
python -m pytest tests/test_web_routes.py::WebCardsTests -v
```

Expected: `AttributeError` or 404 because `GET /api/v1/web/cards` doesn't exist yet.

- [ ] **Step 3: Add cards + card detail endpoints to `web.py`**

```python
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
            a.id::text      AS asset_id,
            a.name,
            a.set_name,
            a.category      AS card_type,
            s.label         AS signal,
            s.price_delta_pct,
            s.liquidity_score,
            tcg.price       AS tcg_price,
            ebay.price      AS ebay_price,
            vol.cnt         AS volume_24h,
            NULL::text      AS image_url
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
            a.id::text      AS asset_id,
            a.name,
            a.set_name,
            a.category      AS card_type,
            s.label         AS signal,
            s.price_delta_pct,
            s.liquidity_score,
            tcg.price       AS tcg_price,
            ebay.price      AS ebay_price,
            NULL::text      AS image_url,
            CASE WHEN tcg.price > 0 AND ebay.price IS NOT NULL
                 THEN ROUND(((tcg.price - ebay.price) / tcg.price * 100)::numeric, 1)
                 ELSE NULL END AS spread_pct
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
            DATE(captured_at) AS date,
            AVG(price) FILTER (WHERE source = 'pokemon_tcg_api') AS tcg_price,
            AVG(price) FILTER (WHERE source = 'ebay_sold')       AS ebay_price
        FROM price_history
        WHERE asset_id = :asset_id::uuid
          AND captured_at >= NOW() - INTERVAL '30 days'
        GROUP BY DATE(captured_at)
        ORDER BY date ASC
    """), {"asset_id": asset_id}).fetchall()

    return {
        **dict(row._mapping),
        "price_history": [
            {"date": str(h.date),
             "tcg_price": float(h.tcg_price) if h.tcg_price else None,
             "ebay_price": float(h.ebay_price) if h.ebay_price else None}
            for h in history
        ],
    }
```

- [ ] **Step 4: Run — expect PASS**

```bash
python -m pytest tests/test_web_routes.py::WebCardsTests -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/web.py tests/test_web_routes.py
git commit -m "feat(backend): web.py cards list + card detail endpoints with tests"
```

---

### Task 14: `web.py` — alerts

- [ ] **Step 1: Add alerts test to `tests/test_web_routes.py`**

```python
class WebAlertsTests(TestCase):
    def _make_client(self, mock_session):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_database] = lambda: iter([mock_session])
        return TestClient(app)

    def test_alerts_returns_shape(self):
        mock_session = MagicMock()
        mock_session.execute.return_value.fetchall.return_value = []
        client = self._make_client(mock_session)
        response = client.get("/api/v1/web/alerts")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("alerts", data)
        self.assertIn("total", data)
        self.assertIsInstance(data["alerts"], list)

    def test_alerts_high_filter_accepted(self):
        mock_session = MagicMock()
        mock_session.execute.return_value.fetchall.return_value = []
        client = self._make_client(mock_session)
        response = client.get("/api/v1/web/alerts?filter=HIGH")
        self.assertEqual(response.status_code, 200)
```

- [ ] **Step 2: Run — expect FAIL**

```bash
python -m pytest tests/test_web_routes.py::WebAlertsTests -v
```

- [ ] **Step 3: Add alerts endpoint to `web.py`**

```python
@router.get("/alerts")
def web_alerts(
    filter: str = Query(default="ALL"),
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_database),
):
    extra = ""
    if filter == "HIGH":
        extra = "AND sub.current_signal = 'BREAKOUT'"

    rows = db.execute(text(f"""
        SELECT
            sub.id::text        AS id,
            sub.asset_id::text  AS asset_id,
            a.name              AS card_name,
            sub.previous_signal,
            sub.current_signal,
            sub.price_delta_pct,
            sub.computed_at     AS created_at,
            CASE sub.current_signal
                WHEN 'BREAKOUT' THEN 'high'
                WHEN 'MOVE'     THEN 'medium'
                ELSE 'low'
            END                 AS severity
        FROM (
            SELECT
                id, asset_id,
                label AS current_signal,
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

- [ ] **Step 4: Run — expect PASS**

```bash
python -m pytest tests/test_web_routes.py -v
```

Expected: all tests PASS. Also run full suite to confirm no regressions:

```bash
python -m pytest --tb=short -q
```

Expected: 138 existing tests + new web tests all pass. If count is higher that's fine (new tests added). Zero failures.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/web.py tests/test_web_routes.py
git commit -m "feat(backend): web.py alerts endpoint with LAG() transitions + tests"
```

---

## Phase 4 — Integration

### Task 15: Register web router + SPA serving

**Files:**
- Modify: `backend/app/api/router.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/site.py`

- [ ] **Step 1: Register web router in `backend/app/api/router.py`**

Open `backend/app/api/router.py`. Add at the top with other imports:

```python
from backend.app.api.routes.web import router as web_router
```

Add after the existing `api_router.include_router(...)` lines:

```python
api_router.include_router(web_router)
```

- [ ] **Step 2: Verify registration with curl**

```bash
cd c:/Flashcard-planet
uvicorn backend.app.main:app --port 8080 &
sleep 3
curl -s http://localhost:8080/api/v1/web/stats | python -m json.tool
```

Expected: JSON with `total_assets`, `signal_counts`, etc. Kill the server after.

- [ ] **Step 3: Update `backend/app/site.py`** — replace the SSR route handler. The existing file has many HTML-returning routes. Replace the entire route section with:

```python
# Keep ONLY these at the bottom of site.py — remove all HTML-returning @router.get routes
from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path

router = APIRouter(include_in_schema=False)
_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

@router.get("/{full_path:path}")
async def serve_spa(full_path: str):
    index = _DIST / "index.html"
    if not index.exists():
        return JSONResponse(
            {"error": "Frontend not built. Run: cd frontend && npm run build"},
            status_code=503,
        )
    return FileResponse(index)
```

**Important:** Before removing existing routes, run the existing test suite to record baseline:

```bash
python -m pytest --tb=short -q 2>&1 | tail -5
```

Note the pass count. After modifying `site.py`, run again and confirm the same count (or higher if SSR tests are now removed intentionally).

- [ ] **Step 4: Update `backend/app/main.py`** — add static file mount. Find the `lifespan` and `app =` lines. Add the static mount and re-check catch-all order. The additions go after existing `app.include_router(...)` calls but before `app.include_router(site_router)`:

```python
from fastapi.staticfiles import StaticFiles
from pathlib import Path

_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

# Add after API routers, before site_router:
if (_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="spa-assets")
```

Confirm `app.include_router(site_router)` is still the last `include_router` call in `main.py`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/router.py backend/app/main.py backend/app/site.py
git commit -m "feat(backend): register web router + SPA serving via site.py catch-all"
```

---

### Task 16: Build frontend + swap mocks + end-to-end verify

- [ ] **Step 1: Build the frontend**

```bash
cd c:/Flashcard-planet/frontend && npm run build
```

Expected: `dist/` directory created, `dist/index.html` exists, `dist/assets/` contains JS/CSS bundles. No build errors.

- [ ] **Step 2: Start full stack and verify SPA is served**

```bash
cd c:/Flashcard-planet
uvicorn backend.app.main:app --port 8080
```

In a second terminal:

```bash
curl -s http://localhost:8080/ | grep -o '<title>[^<]*</title>'
```

Expected: `<title>Vite App</title>` (or whatever the frontend title is). Also verify a deep path doesn't 404:

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/market/some-uuid
```

Expected: `200` (serves `index.html`).

- [ ] **Step 3: curl-verify each real endpoint before swapping**

```bash
curl -s http://localhost:8080/api/v1/web/stats | python -m json.tool
curl -s http://localhost:8080/api/v1/web/ticker | python -m json.tool
curl -s "http://localhost:8080/api/v1/web/cards?limit=3" | python -m json.tool
curl -s "http://localhost:8080/api/v1/web/alerts?limit=5" | python -m json.tool
```

Expected: all return JSON, no 500 errors. Note an actual `asset_id` UUID from the cards response for the next curl.

```bash
# Use a UUID from the cards response above, e.g.:
curl -s http://localhost:8080/api/v1/web/cards/<uuid-from-above> | python -m json.tool
```

Expected: card detail with `price_history` array.

- [ ] **Step 4: Swap `fetchStats` in `frontend/src/api/api.ts`**

```typescript
export async function fetchStats(): Promise<MarketStats> {
  const res = await fetch(`${BASE}/api/v1/web/stats`)
  if (!res.ok) throw new Error('stats fetch failed')
  return res.json()
}
```

Run `npm run dev`, open `/market`. Confirm stat tiles show real numbers (2897 assets, real signal counts).

- [ ] **Step 5: Swap `fetchTicker`**

```typescript
export async function fetchTicker(): Promise<TickerItem[]> {
  const res = await fetch(`${BASE}/api/v1/web/ticker`)
  if (!res.ok) throw new Error('ticker fetch failed')
  return res.json()
}
```

Refresh `/`. Confirm ticker bar shows real card names with real delta percentages.

- [ ] **Step 6: Swap `fetchCards`**

```typescript
export async function fetchCards(params: {
  signal?: Signal | 'ALL'
  sort?: 'change' | 'price' | 'volume'
  limit?: number
  offset?: number
}): Promise<CardsResponse> {
  const { signal = 'ALL', sort = 'change', limit = 50, offset = 0 } = params
  const qs = new URLSearchParams({
    signal, sort, limit: String(limit), offset: String(offset),
  })
  const res = await fetch(`${BASE}/api/v1/web/cards?${qs}`)
  if (!res.ok) throw new Error('cards fetch failed')
  return res.json()
}
```

Refresh `/market`. Confirm real card names load. Try filter pills — grid re-fetches.

- [ ] **Step 7: Swap `fetchCard`**

```typescript
export async function fetchCard(assetId: string): Promise<CardDetail> {
  const res = await fetch(`${BASE}/api/v1/web/cards/${assetId}`)
  if (!res.ok) throw new Error('card fetch failed')
  return res.json()
}
```

Click a card from the dashboard. Confirm detail page loads real data, area chart shows real price history.

- [ ] **Step 8: Swap `fetchAlerts`**

```typescript
export async function fetchAlerts(params: {
  filter?: 'ALL' | 'HIGH' | 'UNREAD'
  limit?: number
}): Promise<AlertsResponse> {
  const qs = new URLSearchParams({
    filter: params.filter ?? 'ALL',
    limit: String(params.limit ?? 50),
  })
  const res = await fetch(`${BASE}/api/v1/web/alerts?${qs}`)
  if (!res.ok) throw new Error('alerts fetch failed')
  return res.json()
}
```

Visit `/alerts`. If `asset_signal_history` has transitions, real alerts appear. If the table is sparse (all signals were computed in one batch with no history), alerts list will be empty — that's correct behavior, not a bug.

- [ ] **Step 9: Final build + full-stack check**

```bash
cd frontend && npm run build
cd .. && uvicorn backend.app.main:app --port 8080
```

In browser, visit `http://localhost:8080` (not 5173 — the built version served by FastAPI). Navigate all 4 pages. Navigate directly to `http://localhost:8080/market` and `http://localhost:8080/alerts` — confirm no 404.

- [ ] **Step 10: Run full test suite**

```bash
python -m pytest --tb=short -q
```

Expected: all tests pass (138 original + new web tests).

- [ ] **Step 11: Commit**

```bash
cd c:/Flashcard-planet
git add frontend/src/api/api.ts frontend/dist/
git commit -m "feat: swap all api.ts mocks to real endpoints — full stack connected"
```

---

## Done Checklist

- [ ] `npm run dev` — all 4 pages render with mock data, no TS errors, no console errors
- [ ] Signal labels are BREAKOUT / MOVE / WATCH / IDLE / `· · ·` — never BUY / SELL
- [ ] `INSUFFICIENT_DATA` badge uses dashed border (`badge-nodata` class)
- [ ] Filter tabs cover all real signal labels
- [ ] Alert rows show `IDLE → BREAKOUT` transition text
- [ ] Mark read / mark all read persists across page refresh
- [ ] All 5 `curl` endpoint checks return valid JSON
- [ ] `npm run build` produces `dist/` without errors
- [ ] Direct URL `/market/<uuid>` served by FastAPI returns 200 (not 404)
- [ ] No hardcoded colors in component files
- [ ] `python -m pytest --tb=short -q` — zero failures
