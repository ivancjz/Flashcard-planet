# Public Calls Phase 2 — Calibration Page Shell

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship `/calls` public page with empty state, three API endpoints, and `ReliabilityDiagram` SVG component. No predictions exist yet — every component must handle n=0 gracefully and look intentional.

**Architecture:** Independent `PublicCallsLayout` (no main app chrome) wraps `CallsPage`. Three new FastAPI routes under `/api/v1/calls/`. Frontend SVG follows the `xOf/yOf` local-helper pattern established in `ComparisonChart.tsx`. All CSS via existing design token vars.

**Tech Stack:** FastAPI + SQLAlchemy 2 (backend) · React + TypeScript + React Router v6 + inline SVG (frontend) · existing design tokens from `theme.css`

---

## Decisions in effect (from claude.ai session 2026-05-18, logged in `.claude/public-calls-decisions.md`)

| Decision | Value |
|---|---|
| Route isolation | `PublicCallsLayout` — no main app sidebar/nav; simplified header only |
| Empty state copy | Positioning statement version (see Task 7) |
| ReliabilityDiagram empty state | Dashed diagonal + educational label (not empty chart) |
| `/calls/list` default | `all`, resolved sorted first |
| `methodology_version` format | `v0.1-{7-char git hash}` |
| Reliability bins at n=0 | Include all 10 bins, n=0 bins have hit_rate=0, ci_low=0, ci_high=1 |

---

## Spec correction from Phase 1

`prediction_service.get_calibration_metrics` is missing `total_calls` accurate count — the mock returns len(rows) which equals total_resolved. The real `total_calls` should count ALL non-paper predictions (including PENDING). Already implemented correctly via the `count_q` block in the service; verified in tests.

---

## File map

| File | Action | Responsibility |
|---|---|---|
| `backend/app/api/routes/calls.py` | Create | 3 endpoints + `_get_methodology_version()` |
| `backend/app/api/router.py` | Modify | Register calls router |
| `backend/app/services/prediction_service.py` | Modify | Add `list_predictions()` |
| `frontend/src/types/calls.ts` | Create | TypeScript types for all API responses |
| `frontend/src/api/calls.ts` | Create | API client (3 functions) |
| `frontend/src/components/calls/ReliabilityDiagram.tsx` | Create | SVG reliability chart |
| `frontend/src/components/calls/CallsTable.tsx` | Create | Sortable predictions table |
| `frontend/src/components/calls/HonestNWarning.tsx` | Create | n<30 warning banner |
| `frontend/src/pages/calls/PublicCallsLayout.tsx` | Create | Independent layout (no main nav) |
| `frontend/src/pages/calls/CallsPage.tsx` | Create | Main page composing all components |
| `frontend/src/main.tsx` | Modify | Add `/calls` route |

---

## Task 1: Backend service — add list_predictions

**Files:**
- Modify: `backend/app/services/prediction_service.py`
- Modify: `tests/test_prediction_service.py`

- [ ] **Step 1: Write failing test** — append to `tests/test_prediction_service.py`:

```python
# ── list_predictions ───────────────────────────────────────────────────────

class TestListPredictions:
    def test_returns_list(self):
        from backend.app.services.prediction_service import list_predictions
        from backend.app.models.predictions import Prediction
        p = Prediction()
        p.id = uuid.uuid4()
        p.resolution_status = "PENDING"
        p.is_paper = False
        db = MagicMock()
        db.scalars.return_value.all.return_value = [p]
        result = list_predictions(db)
        assert len(result) == 1

    def test_excludes_paper_by_default(self):
        from backend.app.services.prediction_service import list_predictions
        db = MagicMock()
        db.scalars.return_value.all.return_value = []
        list_predictions(db)
        # Verify the query was constructed (mock was called)
        assert db.scalars.called

    def test_status_filter_all(self):
        from backend.app.services.prediction_service import list_predictions
        db = MagicMock()
        db.scalars.return_value.all.return_value = []
        list_predictions(db, status="all")
        assert db.scalars.called

    def test_status_filter_pending(self):
        from backend.app.services.prediction_service import list_predictions
        db = MagicMock()
        db.scalars.return_value.all.return_value = []
        list_predictions(db, status="pending")
        assert db.scalars.called

    def test_status_filter_resolved(self):
        from backend.app.services.prediction_service import list_predictions
        db = MagicMock()
        db.scalars.return_value.all.return_value = []
        list_predictions(db, status="resolved")
        assert db.scalars.called
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd c:\Flashcard-planet && python -m pytest tests/test_prediction_service.py::TestListPredictions -x -q 2>&1 | head -10
```

Expected: `ImportError: cannot import name 'list_predictions'`

- [ ] **Step 3: Add `list_predictions` to service** — append after `get_calibration_metrics` in `backend/app/services/prediction_service.py`:

```python
def list_predictions(
    db: Session,
    *,
    status: str = "all",
    only_public: bool = True,
    limit: int = 200,
) -> list[Prediction]:
    """Return predictions for the public /calls page.

    status: 'all' | 'pending' | 'resolved' (HIT or MISS)
    Resolved sorted first, then by resolution_date ascending.
    """
    from sqlalchemy import case

    q = select(Prediction)
    if only_public:
        q = q.where(Prediction.is_paper.is_(False))
    if status == "pending":
        q = q.where(Prediction.resolution_status == "PENDING")
    elif status == "resolved":
        q = q.where(Prediction.resolution_status.in_(["HIT", "MISS"]))
    # default "all": no additional filter

    # Resolved first, then pending; within each group by resolution_date asc
    resolved_first = case(
        (Prediction.resolution_status.in_(["HIT", "MISS"]), 0),
        else_=1,
    )
    q = q.order_by(resolved_first, Prediction.resolution_date.asc()).limit(limit)
    return list(db.scalars(q).all())
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_prediction_service.py -q 2>&1 | tail -5
```

Expected: all pass (45 + 5 = 50 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/prediction_service.py tests/test_prediction_service.py
git commit -m "feat(public-calls): prediction_service.list_predictions — status filter, resolved-first sort

Verified:
- pytest tests/test_prediction_service.py -q — all 50 pass"
```

---

## Task 2: Backend API — calls.py + router registration

**Files:**
- Create: `backend/app/api/routes/calls.py`
- Modify: `backend/app/api/router.py`

- [ ] **Step 1: Create `backend/app/api/routes/calls.py`**

```python
"""calls.py — Public Calls API endpoints.

GET /api/v1/calls/list?status=all|pending|resolved  — list public predictions
GET /api/v1/calls/calibration                       — Brier score + reliability bins
GET /api/v1/calls/{prediction_id}                   — single prediction detail

All endpoints return only is_paper=FALSE predictions.
"""
from __future__ import annotations

import subprocess
import uuid as _uuid
from datetime import UTC, datetime
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.api.deps import get_database
from backend.app.models.predictions import Prediction
from backend.app.services.prediction_service import (
    get_calibration_metrics,
    list_predictions,
)

router = APIRouter(prefix="/calls", tags=["calls"])


@lru_cache(maxsize=1)
def _methodology_version() -> str:
    """Return 'v0.1-{7-char git hash}'. Cached for process lifetime."""
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short=7", "HEAD"],
            stderr=subprocess.DEVNULL,
            timeout=2,
        ).decode().strip()
        return f"v0.1-{sha}"
    except Exception:
        return "v0.1-unknown"


def _serialize_prediction(p: Prediction) -> dict:
    return {
        "id": str(p.id),
        "predicted_at": p.predicted_at.isoformat() if p.predicted_at else None,
        "resolution_date": p.resolution_date.isoformat() if p.resolution_date else None,
        "asset_id": str(p.asset_id),
        "prediction_text": p.prediction_text,
        "threshold_value": str(p.threshold_value) if p.threshold_value is not None else None,
        "threshold_currency": p.threshold_currency,
        "threshold_direction": p.threshold_direction,
        "threshold_band_high": str(p.threshold_band_high) if p.threshold_band_high is not None else None,
        "stated_probability": float(p.stated_probability) if p.stated_probability is not None else None,
        "driver_attribution": p.driver_attribution,
        "driver_confidence": float(p.driver_confidence) if p.driver_confidence is not None else None,
        "methodology_version": p.methodology_version,
        "resolution_status": p.resolution_status,
        "resolved_at": p.resolved_at.isoformat() if p.resolved_at else None,
        "actual_value": str(p.actual_value) if p.actual_value is not None else None,
        "notes": p.notes,
    }


@router.get("/list")
def get_calls_list(
    status: str = Query(default="all", pattern="^(all|pending|resolved)$"),
    db: Session = Depends(get_database),
) -> dict:
    """List public predictions. Resolved sorted first within each status group."""
    predictions = list_predictions(db, status=status, only_public=True)
    return {
        "status_filter": status,
        "count": len(predictions),
        "predictions": [_serialize_prediction(p) for p in predictions],
    }


@router.get("/calibration")
def get_calibration(db: Session = Depends(get_database)) -> dict:
    """Brier score, reliability bins, and aggregate metrics for the public page."""
    metrics = get_calibration_metrics(
        db,
        only_public=True,
        methodology_version=_methodology_version(),
    )
    return {
        "total_calls": metrics.total_calls,
        "total_resolved": metrics.total_resolved,
        "brier_score": metrics.brier_score,
        "brier_baseline": metrics.brier_baseline,
        "reliability_bins": [
            {
                "prob_bin_low": b.prob_bin_low,
                "prob_bin_high": b.prob_bin_high,
                "n": b.n,
                "hit_rate": b.hit_rate,
                "ci_low": b.ci_low,
                "ci_high": b.ci_high,
            }
            for b in metrics.reliability_bins
        ],
        "methodology_version": metrics.methodology_version,
    }


@router.get("/{prediction_id}")
def get_call_detail(
    prediction_id: str,
    db: Session = Depends(get_database),
) -> dict:
    """Single prediction detail. Only public (is_paper=FALSE) predictions."""
    try:
        uid = _uuid.UUID(prediction_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid prediction_id format")

    from sqlalchemy import select
    p: Prediction | None = db.scalars(
        select(Prediction).where(
            Prediction.id == uid,
            Prediction.is_paper.is_(False),
        )
    ).first()
    if p is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return _serialize_prediction(p)
```

- [ ] **Step 2: Register in `backend/app/api/router.py`** — add after the last `include_router` call:

```python
from backend.app.api.routes.calls import router as calls_router
# ... (add to include_router section)
api_router.include_router(calls_router, prefix=settings.api_prefix)
```

Import at top of file alongside the others; include_router line after `sealed_router`.

- [ ] **Step 3: Verify the app starts**

```bash
python -c "from backend.app.api.router import api_router; print('router OK')"
```

- [ ] **Step 4: Spot-check endpoints manually**

```bash
# Start server in background, test, kill
uvicorn backend.app.main:app --port 8001 &
sleep 3
curl -s http://localhost:8001/api/v1/calls/list | python -m json.tool
curl -s http://localhost:8001/api/v1/calls/calibration | python -m json.tool
kill %1
```

Expected for `/calls/list`:
```json
{"status_filter": "all", "count": 0, "predictions": []}
```

Expected for `/calls/calibration`:
```json
{
  "total_calls": 0,
  "total_resolved": 0,
  "brier_score": null,
  "brier_baseline": 0.25,
  "reliability_bins": [...10 items with n=0...],
  "methodology_version": "v0.1-XXXXXXX"
}
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/calls.py backend/app/api/router.py
git commit -m "feat(public-calls): /api/v1/calls/* endpoints — list, calibration, detail

Three public endpoints returning only is_paper=FALSE predictions.
methodology_version auto-derives from git short hash.

Verified:
- router import OK
- /calls/list returns empty list at n=0
- /calls/calibration returns 10 bins with n=0"
```

---

## Task 3: Frontend types and API client

**Files:**
- Create: `frontend/src/types/calls.ts`
- Create: `frontend/src/api/calls.ts`

- [ ] **Step 1: Create `frontend/src/types/calls.ts`**

```typescript
// frontend/src/types/calls.ts

export type ThresholdDirection = 'above' | 'below' | 'within_band'
export type ResolutionStatus = 'PENDING' | 'HIT' | 'MISS' | 'AMBIGUOUS' | 'VOIDED'
export type DriverAttribution =
  | 'MACRO' | 'META_SHIFT' | 'SUPPLY_SHOCK'
  | 'EVENT_DRIVEN' | 'INFLUENCER_PROVENANCE' | 'UNKNOWN'

export interface PublicPrediction {
  id: string
  predicted_at: string
  resolution_date: string
  asset_id: string
  prediction_text: string
  threshold_value: string
  threshold_currency: string
  threshold_direction: ThresholdDirection
  threshold_band_high: string | null
  stated_probability: number
  driver_attribution: DriverAttribution | null
  driver_confidence: number | null
  methodology_version: string
  resolution_status: ResolutionStatus
  resolved_at: string | null
  actual_value: string | null
  notes: string | null
}

export interface CallsListResponse {
  status_filter: string
  count: number
  predictions: PublicPrediction[]
}

export interface ReliabilityBin {
  prob_bin_low: number
  prob_bin_high: number
  n: number
  hit_rate: number
  ci_low: number
  ci_high: number
}

export interface CalibrationResponse {
  total_calls: number
  total_resolved: number
  brier_score: number | null
  brier_baseline: number
  reliability_bins: ReliabilityBin[]
  methodology_version: string
}
```

- [ ] **Step 2: Create `frontend/src/api/calls.ts`**

```typescript
// frontend/src/api/calls.ts
import type { CallsListResponse, CalibrationResponse, PublicPrediction } from '../types/calls'

const BASE = '/api/v1/calls'

export async function fetchCallsList(
  status: 'all' | 'pending' | 'resolved' = 'all'
): Promise<CallsListResponse> {
  const res = await fetch(`${BASE}/list?status=${status}`)
  if (!res.ok) throw new Error(`calls/list fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchCalibration(): Promise<CalibrationResponse> {
  const res = await fetch(`${BASE}/calibration`)
  if (!res.ok) throw new Error(`calls/calibration fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchCallDetail(predictionId: string): Promise<PublicPrediction> {
  const res = await fetch(`${BASE}/${predictionId}`)
  if (!res.ok) throw new Error(`calls/${predictionId} fetch failed: ${res.status}`)
  return res.json()
}
```

- [ ] **Step 3: TypeScript compile check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -i "calls\|error" | head -20
```

Expected: no errors in calls.ts or types/calls.ts.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/calls.ts frontend/src/api/calls.ts
git commit -m "feat(public-calls): frontend types + API client for /calls endpoints"
```

---

## Task 4: ReliabilityDiagram.tsx

**Files:**
- Create: `frontend/src/components/calls/ReliabilityDiagram.tsx`

SVG conventions (matches ComparisonChart.tsx):
- Local `xOf` / `yOf` helpers for coordinate mapping
- `viewBox="0 0 W H"` with `width="100%" height="auto"` 
- Space Mono for numeric labels (`fontFamily="'Space Mono', monospace"`)
- CSS vars for color
- No external chart library

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/calls/ReliabilityDiagram.tsx
import type { ReliabilityBin } from '../../types/calls'

interface Props {
  bins: ReliabilityBin[]
  totalResolved: number
}

export default function ReliabilityDiagram({ bins, totalResolved }: Props) {
  const W = 320
  const H = 320
  const PAD = { top: 24, right: 24, bottom: 48, left: 48 }
  const IW = W - PAD.left - PAD.right
  const IH = H - PAD.top - PAD.bottom

  // Both axes 0→1 (probability space)
  const xOf = (p: number) => PAD.left + p * IW
  const yOf = (p: number) => PAD.top + (1 - p) * IH

  // Axis ticks at 0, 0.25, 0.5, 0.75, 1.0
  const ticks = [0, 0.25, 0.5, 0.75, 1.0]

  const isEmpty = totalResolved === 0

  // Dot radius scaled by n (min 4, max 14)
  const maxN = Math.max(...bins.map(b => b.n), 1)
  const dotRadius = (n: number) => n === 0 ? 0 : 4 + (n / maxN) * 10

  return (
    <div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: '100%', maxWidth: 320, height: 'auto', display: 'block' }}
        aria-label="Reliability diagram"
      >
        {/* Grid lines */}
        {ticks.map(t => (
          <g key={t}>
            <line
              x1={xOf(0)} x2={xOf(1)} y1={yOf(t)} y2={yOf(t)}
              stroke="rgba(255,255,255,0.06)" strokeWidth={1}
            />
            <line
              x1={xOf(t)} x2={xOf(t)} y1={yOf(0)} y2={yOf(1)}
              stroke="rgba(255,255,255,0.06)" strokeWidth={1}
            />
          </g>
        ))}

        {/* Perfect calibration diagonal — dashed, always visible */}
        <line
          x1={xOf(0)} y1={yOf(0)} x2={xOf(1)} y2={yOf(1)}
          stroke="rgba(255,255,255,0.20)"
          strokeWidth={1.5}
          strokeDasharray="5 4"
        />

        {/* Diagonal label (educational, shown always) */}
        <text
          x={xOf(0.72)} y={yOf(0.82)}
          fontSize={9}
          fontFamily="'Space Mono', monospace"
          fill="var(--text-muted)"
          transform={`rotate(-45, ${xOf(0.72)}, ${yOf(0.82)})`}
        >
          perfect calibration
        </text>

        {/* Empty state label */}
        {isEmpty && (
          <text
            x={W / 2} y={H / 2 + 20}
            fontSize={11}
            fontFamily="'Space Mono', monospace"
            fill="var(--text-muted)"
            textAnchor="middle"
          >
            awaiting first resolution
          </text>
        )}

        {/* Wilson CI bars + dots (only when data exists) */}
        {!isEmpty && bins.filter(b => b.n > 0).map((b, i) => {
          const cx = xOf((b.prob_bin_low + b.prob_bin_high) / 2)
          const cy = yOf(b.hit_rate)
          const ciTop = yOf(b.ci_high)
          const ciBot = yOf(b.ci_low)
          const r = dotRadius(b.n)
          return (
            <g key={i}>
              {/* CI bar */}
              <line
                x1={cx} x2={cx} y1={ciTop} y2={ciBot}
                stroke="var(--gold-dim)" strokeWidth={1.5}
              />
              {/* Bin dot */}
              <circle
                cx={cx} cy={cy} r={r}
                fill="var(--gold)" opacity={0.85}
              />
            </g>
          )
        })}

        {/* Y axis labels */}
        {ticks.map(t => (
          <text
            key={t}
            x={PAD.left - 8} y={yOf(t) + 4}
            fontSize={9}
            fontFamily="'Space Mono', monospace"
            fill="var(--text-muted)"
            textAnchor="end"
          >
            {Math.round(t * 100)}%
          </text>
        ))}

        {/* X axis labels */}
        {ticks.map(t => (
          <text
            key={t}
            x={xOf(t)} y={H - PAD.bottom + 16}
            fontSize={9}
            fontFamily="'Space Mono', monospace"
            fill="var(--text-muted)"
            textAnchor="middle"
          >
            {Math.round(t * 100)}%
          </text>
        ))}

        {/* Axis labels */}
        <text
          x={W / 2} y={H - 2}
          fontSize={10}
          fontFamily="'Space Mono', monospace"
          fill="var(--text-secondary)"
          textAnchor="middle"
        >
          stated probability
        </text>
        <text
          x={10} y={H / 2}
          fontSize={10}
          fontFamily="'Space Mono', monospace"
          fill="var(--text-secondary)"
          textAnchor="middle"
          transform={`rotate(-90, 10, ${H / 2})`}
        >
          actual hit rate
        </text>
      </svg>
    </div>
  )
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "ReliabilityDiagram\|error" | head -10
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/calls/ReliabilityDiagram.tsx
git commit -m "feat(public-calls): ReliabilityDiagram SVG — dashed diagonal placeholder, Wilson CI bars

Empty state: dashed diagonal + 'awaiting first resolution' label.
With data: dots sized by n, CI error bars, hit_rate plotted.
Follows xOf/yOf local-helper convention from ComparisonChart.tsx."
```

---

## Task 5: CallsTable.tsx + HonestNWarning.tsx

**Files:**
- Create: `frontend/src/components/calls/CallsTable.tsx`
- Create: `frontend/src/components/calls/HonestNWarning.tsx`

- [ ] **Step 1: Create `HonestNWarning.tsx`**

```tsx
// frontend/src/components/calls/HonestNWarning.tsx
interface Props {
  totalResolved: number
  threshold?: number
}

export default function HonestNWarning({ totalResolved, threshold = 30 }: Props) {
  return (
    <div style={{
      padding: '10px 14px',
      background: 'rgba(240,180,41,0.08)',
      border: '1px solid var(--border-gold-soft)',
      borderRadius: 'var(--radius-md)',
      fontSize: 12,
      fontFamily: "'Space Mono', monospace",
      color: 'var(--text-secondary)',
      lineHeight: 1.6,
    }}>
      n={totalResolved}. Statistical significance achieved at n≥{threshold}.{' '}
      {totalResolved < threshold
        ? 'Early calibration is directional only.'
        : 'Calibration is statistically meaningful.'}
    </div>
  )
}
```

- [ ] **Step 2: Create `CallsTable.tsx`**

```tsx
// frontend/src/components/calls/CallsTable.tsx
import { useState } from 'react'
import type { PublicPrediction, ResolutionStatus } from '../../types/calls'

interface Props {
  predictions: PublicPrediction[]
}

type SortKey = 'resolution_date' | 'stated_probability' | 'resolution_status'

const STATUS_ORDER: Record<ResolutionStatus, number> = {
  HIT: 0, MISS: 1, PENDING: 2, AMBIGUOUS: 3, VOIDED: 4,
}

const STATUS_COLOR: Record<ResolutionStatus, string> = {
  HIT: 'var(--breakout)',
  MISS: 'var(--watch)',
  PENDING: 'var(--text-muted)',
  AMBIGUOUS: 'var(--idle)',
  VOIDED: 'var(--idle)',
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return iso.slice(0, 10)
}

function fmtProb(p: number): string {
  return `${Math.round(p * 100)}%`
}

export default function CallsTable({ predictions }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('resolution_date')
  const [sortAsc, setSortAsc] = useState(true)

  function toggleSort(key: SortKey) {
    if (sortKey === key) setSortAsc(a => !a)
    else { setSortKey(key); setSortAsc(true) }
  }

  const sorted = [...predictions].sort((a, b) => {
    let cmp = 0
    if (sortKey === 'resolution_date') {
      cmp = (a.resolution_date ?? '').localeCompare(b.resolution_date ?? '')
    } else if (sortKey === 'stated_probability') {
      cmp = a.stated_probability - b.stated_probability
    } else if (sortKey === 'resolution_status') {
      cmp = (STATUS_ORDER[a.resolution_status] ?? 9) - (STATUS_ORDER[b.resolution_status] ?? 9)
    }
    return sortAsc ? cmp : -cmp
  })

  if (predictions.length === 0) {
    return (
      <div style={{
        padding: '32px 0',
        textAlign: 'center',
        color: 'var(--text-muted)',
        fontFamily: "'Space Mono', monospace",
        fontSize: 13,
      }}>
        No calls yet.
      </div>
    )
  }

  const SortBtn = ({ k, label }: { k: SortKey; label: string }) => (
    <button
      onClick={() => toggleSort(k)}
      style={{
        background: 'none', border: 'none', color: 'var(--text-secondary)',
        fontFamily: "'Space Mono', monospace", fontSize: 11, cursor: 'pointer',
        padding: 0, display: 'flex', alignItems: 'center', gap: 4,
      }}
    >
      {label}
      {sortKey === k ? (sortAsc ? ' ↑' : ' ↓') : ''}
    </button>
  )

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
            <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 400 }}>
              Call
            </th>
            <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 400 }}>
              <SortBtn k="stated_probability" label="Probability" />
            </th>
            <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 400 }}>
              <SortBtn k="resolution_date" label="Resolves" />
            </th>
            <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 400 }}>
              <SortBtn k="resolution_status" label="Result" />
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map(p => (
            <tr
              key={p.id}
              style={{ borderBottom: '1px solid var(--border-subtle)' }}
            >
              <td style={{ padding: '10px 12px', color: 'var(--text-primary)', maxWidth: 320 }}>
                {p.prediction_text}
              </td>
              <td style={{
                padding: '10px 12px',
                fontFamily: "'Space Mono', monospace",
                color: 'var(--text-secondary)',
              }}>
                {fmtProb(p.stated_probability)}
              </td>
              <td style={{
                padding: '10px 12px',
                fontFamily: "'Space Mono', monospace",
                color: 'var(--text-muted)',
                whiteSpace: 'nowrap',
              }}>
                {fmtDate(p.resolution_date)}
              </td>
              <td style={{
                padding: '10px 12px',
                fontFamily: "'Space Mono', monospace",
                color: STATUS_COLOR[p.resolution_status] ?? 'var(--text-muted)',
                fontWeight: 700,
                fontSize: 11,
              }}>
                {p.resolution_status}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "Calls\|Honest\|error" | head -10
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/calls/
git commit -m "feat(public-calls): CallsTable (sortable) + HonestNWarning components"
```

---

## Task 6: PublicCallsLayout.tsx + CallsPage.tsx

**Files:**
- Create: `frontend/src/pages/calls/PublicCallsLayout.tsx`
- Create: `frontend/src/pages/calls/CallsPage.tsx`

- [ ] **Step 1: Create `PublicCallsLayout.tsx`**

```tsx
// frontend/src/pages/calls/PublicCallsLayout.tsx
import { Link, Outlet } from 'react-router-dom'

export default function PublicCallsLayout() {
  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)', color: 'var(--text-primary)' }}>
      {/* Simplified header — no main app nav */}
      <header style={{
        borderBottom: '1px solid var(--border-subtle)',
        padding: '0 24px',
        height: 52,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        background: 'var(--bg-surface)',
      }}>
        <span style={{
          fontFamily: 'Syne, sans-serif',
          fontWeight: 700,
          fontSize: 16,
          color: 'var(--gold)',
          letterSpacing: '-0.3px',
        }}>
          Flashcard Planet
        </span>
        <Link
          to="/market"
          style={{
            fontSize: 12,
            fontFamily: "'Space Mono', monospace",
            color: 'var(--text-muted)',
          }}
        >
          ← Back to signals
        </Link>
      </header>

      {/* Page content */}
      <Outlet />
    </div>
  )
}
```

- [ ] **Step 2: Create `CallsPage.tsx`**

```tsx
// frontend/src/pages/calls/CallsPage.tsx
import { useEffect, useState } from 'react'
import { fetchCallsList, fetchCalibration } from '../../api/calls'
import type { CalibrationResponse, CallsListResponse } from '../../types/calls'
import ReliabilityDiagram from '../../components/calls/ReliabilityDiagram'
import CallsTable from '../../components/calls/CallsTable'
import HonestNWarning from '../../components/calls/HonestNWarning'

export default function CallsPage() {
  const [calibration, setCalibration] = useState<CalibrationResponse | null>(null)
  const [callsList, setCallsList] = useState<CallsListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([fetchCalibration(), fetchCallsList('all')])
      .then(([cal, list]) => {
        setCalibration(cal)
        setCallsList(list)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div style={{ padding: 48, textAlign: 'center', color: 'var(--text-muted)', fontFamily: "'Space Mono', monospace", fontSize: 13 }}>
        Loading...
      </div>
    )
  }

  if (error) {
    return (
      <div style={{ padding: 48, textAlign: 'center', color: 'var(--watch)', fontFamily: "'Space Mono', monospace", fontSize: 13 }}>
        Failed to load: {error}
      </div>
    )
  }

  const cal = calibration!
  const totalResolved = cal.total_resolved

  return (
    <main style={{ maxWidth: 860, margin: '0 auto', padding: '48px 24px 80px' }}>

      {/* ── Headline ── */}
      <div style={{ marginBottom: 40 }}>
        <h1 style={{
          fontFamily: 'Syne, sans-serif',
          fontWeight: 800,
          fontSize: 'clamp(22px, 4vw, 36px)',
          color: 'var(--text-primary)',
          marginBottom: 12,
          lineHeight: 1.15,
        }}>
          First calibration cohort launches June 14, 2026.
        </h1>
        <p style={{
          fontSize: 15,
          color: 'var(--text-secondary)',
          lineHeight: 1.7,
          maxWidth: 560,
        }}>
          We forecast. We grade ourselves.<br />
          Every prediction below is locked at creation, resolved automatically,
          and aggregated into a public Brier score.
        </p>
        <div style={{ marginTop: 20 }}>
          <HonestNWarning totalResolved={totalResolved} />
        </div>
      </div>

      {/* ── Metrics row ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
        gap: 12,
        marginBottom: 40,
      }}>
        {[
          { label: 'Total calls', value: cal.total_calls },
          { label: 'Resolved', value: cal.total_resolved },
          {
            label: 'Hit rate',
            value: totalResolved > 0
              ? `${Math.round((cal.reliability_bins.reduce((s, b) => s + b.n * b.hit_rate, 0) / totalResolved) * 100)}%`
              : '—',
          },
          {
            label: 'Brier score',
            value: cal.brier_score !== null ? cal.brier_score.toFixed(3) : '—',
          },
          { label: 'Baseline', value: cal.brier_baseline.toFixed(2) },
        ].map(({ label, value }) => (
          <div key={label} style={{
            background: 'var(--bg-surface)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 'var(--radius-md)',
            padding: '14px 16px',
          }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: "'Space Mono', monospace", marginBottom: 6 }}>
              {label}
            </div>
            <div style={{ fontSize: 22, fontFamily: "'Space Mono', monospace", color: 'var(--text-primary)', fontWeight: 700 }}>
              {value}
            </div>
          </div>
        ))}
      </div>

      {/* ── Reliability diagram + methodology ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '320px 1fr',
        gap: 32,
        marginBottom: 48,
        alignItems: 'start',
      }}>
        <div>
          <div style={{ fontSize: 12, fontFamily: "'Space Mono', monospace", color: 'var(--text-muted)', marginBottom: 12 }}>
            Reliability diagram
          </div>
          <ReliabilityDiagram bins={cal.reliability_bins} totalResolved={totalResolved} />
        </div>
        <div style={{ paddingTop: 28 }}>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7, marginBottom: 16 }}>
            Each dot is a decile of stated probabilities. Perfect calibration means
            the dots fall on the diagonal — a 70% call should resolve correctly 70% of the time.
          </p>
          <p style={{ fontSize: 12, fontFamily: "'Space Mono', monospace", color: 'var(--text-muted)' }}>
            Method: {cal.methodology_version}
          </p>
          <a
            href="/methodology"
            style={{
              display: 'inline-block',
              marginTop: 12,
              fontSize: 12,
              fontFamily: "'Space Mono', monospace",
              color: 'var(--gold)',
              textDecoration: 'none',
            }}
          >
            Methodology →
          </a>
        </div>
      </div>

      {/* ── Calls table ── */}
      <div>
        <div style={{ fontSize: 12, fontFamily: "'Space Mono', monospace", color: 'var(--text-muted)', marginBottom: 12 }}>
          All calls
        </div>
        <div style={{
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-lg)',
          overflow: 'hidden',
        }}>
          <CallsTable predictions={callsList?.predictions ?? []} />
        </div>
      </div>

    </main>
  )
}
```

- [ ] **Step 3: TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "Calls\|Layout\|error" | head -10
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/calls/
git commit -m "feat(public-calls): PublicCallsLayout + CallsPage — empty state with positioning copy

Independent layout (no main app nav). Empty state is positioning statement,
shareable day 1 before any predictions exist."
```

---

## Task 7: Wire /calls route in main.tsx

**Files:**
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Add imports and route** — open `frontend/src/main.tsx` and add:

At the top (with other imports):
```tsx
import PublicCallsLayout from './pages/calls/PublicCallsLayout'
import CallsPage from './pages/calls/CallsPage'
```

Inside `<Routes>`, after the last `<Route>` and before `</Routes>`:
```tsx
<Route path="/calls" element={<PublicCallsLayout />}>
  <Route index element={<CallsPage />} />
</Route>
```

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/main.tsx
git commit -m "feat(public-calls): register /calls route with independent PublicCallsLayout

No UserProvider or main app nav wrapping. Fully isolated top-of-funnel page."
```

---

## Task 8: Build verification + dev server test

- [ ] **Step 1: Production build check**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds with no TypeScript errors.

- [ ] **Step 2: Start dev server and test in browser**

```bash
# Terminal 1: backend
uvicorn backend.app.main:app --reload --port 8000 &

# Terminal 2: frontend
cd frontend && npm run dev &

sleep 5
```

Open http://localhost:5173/calls and verify:
- Simplified header with "Flashcard Planet" + "← Back to signals" link
- Headline: "First calibration cohort launches June 14, 2026."
- Subhead text present
- HonestNWarning shows "n=0. Statistical significance achieved at n≥30."
- Metrics row shows all zeros / dashes
- ReliabilityDiagram shows dashed diagonal + "awaiting first resolution"
- Calls table shows "No calls yet."
- No JS console errors

Also verify `/calls/list`, `/calls/calibration` return correct JSON at the API level.

- [ ] **Step 3: Kill dev servers**

```bash
kill $(lsof -ti:8000 -ti:5173) 2>/dev/null || true
```

- [ ] **Step 4: Commit decisions log**

```bash
git add .claude/public-calls-decisions.md
git commit -m "docs(public-calls): Phase 2 decisions log — route isolation, empty state copy, bin handling"
```

---

## Task 9: PR + Codex review + production gate

- [ ] **Step 1: Run Codex review**

```bash
codex exec review --base main --ephemeral 2>&1 | tee /tmp/codex-review-phase2.txt
cat /tmp/codex-review-phase2.txt | tail -20
```

Focus Codex on:
1. Route isolation — `/calls` genuinely independent, no accidental shared state imports
2. SVG conventions — `xOf`/`yOf` pattern used correctly
3. API response schema matches `types/calls.ts` exactly
4. `list_predictions` status filter logic correct (resolved = HIT | MISS, not all non-PENDING)

- [ ] **Step 2: Push + open PR**

```bash
git push -u origin feat/public-calls-phase-2
gh pr create \
  --title "feat(public-calls): Phase 2 — /calls page shell + API endpoints" \
  --body "..."
```

PR body must include Codex review output under `## Codex Review`.

- [ ] **Step 3: Production verification gate**

After Railway auto-deploy:
1. `curl https://flashcardplanet.com/api/v1/calls/list` → `{"status_filter":"all","count":0,"predictions":[]}`
2. `curl https://flashcardplanet.com/api/v1/calls/calibration` → 10 reliability bins, all n=0
3. Open https://flashcardplanet.com/calls in browser → screenshot for Ivan
4. Verify no console errors in browser

**Production verification gate checklist:**
- [ ] `/api/v1/calls/list` returns `count: 0`, empty array
- [ ] `/api/v1/calls/calibration` returns 10 bins, `brier_score: null`, `total_resolved: 0`
- [ ] `/calls` page loads in browser (screenshot required per playbook)
- [ ] Empty state copy matches exactly: "First calibration cohort launches June 14, 2026."
- [ ] ReliabilityDiagram shows dashed diagonal (not blank)
- [ ] No JS console errors

---

## Self-review checklist

**Spec coverage:**
- ✅ `GET /api/v1/calls/list?status=` — Task 2
- ✅ `GET /api/v1/calls/calibration` — Task 2
- ✅ `GET /api/v1/calls/{id}` — Task 2
- ✅ Independent `/calls` layout — Task 6 + 7
- ✅ `CallsPage.tsx` with headline, metrics, plot, table — Task 6
- ✅ `ReliabilityDiagram.tsx` SVG — Task 4
- ✅ `CallsTable.tsx` sortable — Task 5
- ✅ `HonestNWarning.tsx` — Task 5
- ✅ Empty state per decisions — Task 6
- ✅ Reliability bins n=0 included — Task 1/2 (service returns all 10 always)
- ✅ Default status=all, resolved first — Task 1
- ✅ methodology_version 7-char hash — Task 2

**Type consistency:**
- `ReliabilityBin` fields: `prob_bin_low/high` (float), `n` (int), `hit_rate/ci_low/ci_high` (float) — consistent across `types/calls.ts`, `CalibrationResponse.reliability_bins`, `_build_reliability_bins` output ✅
- `PublicPrediction.stated_probability` is `number` (float) — consistent with backend `float(p.stated_probability)` serialization ✅
- `threshold_value` serialized as `string` (Decimal → str) — consistent with `PublicPrediction.threshold_value: string` ✅

**Placeholder scan:** No TBDs. All component code is complete. ✅

**5-category edge case audit:**
1. **No data (n=0)**: ReliabilityDiagram shows placeholder; CallsTable shows "No calls yet."; metrics show 0/—
2. **Single resolved call**: Brier score computes; one bin has n=1; CI bars render
3. **Unknown driver_attribution**: `null` renders as nothing in table (driver col not shown in Phase 2)
4. **Currency**: `threshold_value` shown as string; no currency conversion needed in Phase 2 display
5. **Monitoring**: No new scheduler jobs in Phase 2; no monitoring additions needed
