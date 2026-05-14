# Flashcard Planet — Chart Pattern Cheat Sheet
# Source of truth for PriceHistoryChart (Test 3)
# All code blocks are verbatim from the codebase — do NOT paraphrase or rename.

---

## 0. Required input pipeline — MANDATORY before any SVG math

Components receive raw price data from props as `{ time: number, price: number }[]`.
This MUST be converted to `ChartPoint[]` (`{ time, pct }`) before xScale / yOf /
splitIntoSegments are called. The conversion is NOT optional and NOT done by the
chart primitives themselves.

Use `buildExtPoints` (CardDetailPage.tsx:31–41) or an inline equivalent:

```ts
// baseline = first valid price in the series
// pct = ((price - baseline) / baseline) * 100
function buildExtPoints(
  data: { time: number; price: number }[],
  baseline: number
): ChartPoint[] {
  return data.map(d => ({
    time: d.time,
    pct: ((d.price - baseline) / baseline) * 100,
  }))
}
```

Do this separately for each series (TCG, eBay) before passing to splitIntoSegments.
The SVG layer never sees raw prices — only normalized pct values.

---

## 1. Canvas constants (NormalizedChart in CardDetailPage.tsx:55–57)

```ts
const W = 560, H = 180
const PAD = { top: 16, right: 16, bottom: 28, left: 52 }
const IW = W - PAD.left - PAD.right
const IH = H - PAD.top - PAD.bottom
```

---

## 2. Data types (chartUtils.ts:1–9)

```ts
export interface ChartPoint {
  time: number  // ms timestamp
  pct: number   // normalized % change from baseline
}

export interface ChartSegment {
  type: 'solid' | 'gap'
  points: ChartPoint[]
}
```

Note: the chart works on normalized % data, NOT raw prices. Raw prices must be
converted upstream via buildExtPoints (CardDetailPage.tsx:31–41).

---

## 3. xScale — time → pixel x (CardDetailPage.tsx:77–78)

```ts
const timeRange = timeMax - timeMin || 1
const xScale = (t: number) => ((t - timeMin) / timeRange) * IW
```

Used inside `<g transform={`translate(${PAD.left},${PAD.top})`}>` — coordinates
are relative to the inner area, PAD offsets are in the transform, not in xScale.

In ComparisonChart.tsx (no translate, absolute coords):
```ts
const xOf = (t: number) => PAD.left + ((t - timeMin) / (timeMax - timeMin)) * IW
```

---

## 4. yOf — pct → pixel y (CardDetailPage.tsx:83–84)

```ts
const yOf = (pct: number) => IH - ((pct - minY) / rangeY) * IH
const zeroY = Math.min(IH, Math.max(0, yOf(0)))
```

Origin (y=0) is at the TOP of the SVG coordinate system, so higher values = smaller y.
`zeroY` is clamped to [0, IH] so it stays inside the chart even when all values are above/below 0.

In ComparisonChart.tsx (translated origin at top of chart):
```ts
const yOf = (pct: number) => PAD.top + (1 - (pct - yBot) / yRange) * IH
```

---

## 5. splitIntoSegments (chartUtils.ts:13–38)

```ts
const GAP_THRESHOLD_MS = 24 * 60 * 60 * 1000  // 1 day

export function splitIntoSegments(points: ChartPoint[]): ChartSegment[] {
  // splits on gaps > 24h
  // gap bridge segment = { type: 'gap', points: [lastPointBeforeGap, firstPointAfterGap] }
  // continuous run = { type: 'solid', points: [...] }
}
```

Key shape: a `'gap'` segment has exactly 2 points (the bridge endpoints).
Import: `import { splitIntoSegments } from '../lib/chartUtils'`

---

## 6. buildAreaPath (CardDetailPage.tsx:43–48)

```ts
function buildAreaPath(
  points: { time: number; pct: number }[],
  xScale: (t: number) => number,
  yOf: (p: number) => number,
  zeroY: number
): string {
  if (points.length < 2) return ''
  const xs = points.map(p => xScale(p.time))
  const ys = points.map(p => yOf(p.pct))
  return `M ${xs[0]},${zeroY} ${points.map((_, i) => `L ${xs[i]},${ys[i]}`).join(' ')} L ${xs[xs.length - 1]},${zeroY} Z`
}
```

Only called on `solid` segments: `segments.filter(s => s.type === 'solid' && s.points.length >= 2)`

---

## 7. Stroke dash conventions

From CardDetailPage.tsx:172–173 and 193–194:
```ts
// gap segment (both series):
strokeDasharray={seg.type === 'gap' ? '8,4' : '4 2'}   // eBay: always dashed
strokeDasharray={seg.type === 'gap' ? '8,4' : undefined} // TCG: solid normally, dashed in gap

// opacity
opacity={seg.type === 'gap' ? 0.35 : 0.8}   // eBay
opacity={seg.type === 'gap' ? 0.4 : 1}       // TCG
```

---

## 8. End-point dots (CardDetailPage.tsx:178–180, 200–203)

```tsx
// eBay
<circle cx={xScale(last.time)} cy={yOf(last.pct)}
  r={3} fill="var(--breakout)" stroke="var(--bg-base)" strokeWidth={1.5} />

// TCG
<circle cx={xScale(last.time)} cy={yOf(last.pct)}
  r={4} fill="var(--gold)" stroke="var(--bg-base)" strokeWidth={2} />
```

---

## 9. Gradient defs convention (CardDetailPage.tsx:139–148)

```tsx
<defs>
  <linearGradient id="tcg-norm-grad" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stopColor="var(--gold)" stopOpacity="0.22" />
    <stop offset="100%" stopColor="var(--gold)" stopOpacity="0" />
  </linearGradient>
  <linearGradient id="ebay-norm-grad" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stopColor="var(--breakout)" stopOpacity="0.12" />
    <stop offset="100%" stopColor="var(--breakout)" stopOpacity="0" />
  </linearGradient>
</defs>
```

Referenced as `fill="url(#tcg-norm-grad)"` on area paths.

**color-mix() scope rule:** `stopOpacity` is the ONLY SVG attribute exempted from
the color-mix() requirement. It is a bare SVG numeric (0–1), not a CSS color value,
and CSS functions are not valid there. Every other color-bearing attribute —
`stroke`, `fill`, `stopColor`, CSS `color`, CSS `background`, etc. — must still use
`var(--token)` for solid colors and `color-mix(in srgb, var(--token) N%, transparent)`
for any transparency. Do NOT extend this exemption to any other attribute.

---

## 10. Area rendering pattern (CardDetailPage.tsx:163–166, 187–189)

```tsx
{ebaySegments.filter(s => s.type === 'solid' && s.points.length >= 2).map((seg, i) => (
  <path key={`ebay-area-${i}`} d={buildAreaPath(seg.points, xScale, yOf, zeroY)} fill="url(#ebay-norm-grad)" />
))}

{tcgSegments.filter(s => s.type === 'solid' && s.points.length >= 2).map((seg, i) => (
  <path key={`tcg-area-${i}`} d={buildAreaPath(seg.points, xScale, yOf, zeroY)} fill="url(#tcg-norm-grad)" />
))}
```

---

## 11. Line rendering pattern (CardDetailPage.tsx:167–175, 190–198)

```tsx
{ebaySegments.map((seg, i) => {
  const d = seg.points.map((p, j) => `${j === 0 ? 'M' : 'L'} ${xScale(p.time)},${yOf(p.pct)}`).join(' ')
  return (
    <path key={`ebay-${i}`} d={d} fill="none" stroke="var(--breakout)"
      strokeWidth={1.5} strokeLinecap="round"
      strokeDasharray={seg.type === 'gap' ? '8,4' : '4 2'}
      opacity={seg.type === 'gap' ? 0.35 : 0.8}
    />
  )
})}

{tcgSegments.map((seg, i) => {
  const d = seg.points.map((p, j) => `${j === 0 ? 'M' : 'L'} ${xScale(p.time)},${yOf(p.pct)}`).join(' ')
  return (
    <path key={`tcg-${i}`} d={d} fill="none" stroke="var(--gold)"
      strokeWidth={2} strokeLinecap="round"
      strokeDasharray={seg.type === 'gap' ? '8,4' : undefined}
      opacity={seg.type === 'gap' ? 0.4 : 1}
    />
  )
})}
```

---

## 12. Legend rendering (ComparisonChart.tsx:151–163)

```tsx
{series.map((s, i) => (
  <g key={s.id} transform={`translate(${W - PAD.right + 8}, ${PAD.top + i * 20})`}>
    <line x1={0} y1={5} x2={12} y2={5} stroke={s.color} strokeWidth={2} />
    <circle cx={6} cy={5} r={2.5} fill={s.color} />
    <text
      x={16} y={9}
      fontSize={10} fontFamily="'Syne', sans-serif"
      fill="var(--text-secondary)"
    >
      {label}
    </text>
  </g>
))}
```

For PriceHistoryChart: two fixed legend entries at top-right corner of SVG, outside the `<g transform>`.

---

## 13. Y-axis ticks (ComparisonChart.tsx:64–70 / CardDetailPage.tsx:86–91)

```ts
const rawStep = (maxY - minY) / 4
const mag = Math.pow(10, Math.floor(Math.log10(rawStep || 1)))
const tickStep = Math.ceil(rawStep / mag) * mag || 5
const ticks = new Set<number>([0])
for (let t = Math.floor(minY / tickStep) * tickStep; t <= maxY + tickStep; t += tickStep)
  ticks.add(Math.round(t))
```

Labels: `t >= 0 ? \`+${t}%\` : \`${t}%\`` in Space Mono 9px, fill="var(--text-secondary)" (or text-muted).

---

## 14. SVG wrapper pattern (CardDetailPage.tsx:138)

```tsx
<svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block' }}>
```

The outer `<div>` wraps interaction (cursor, mousemove handler).

---

## 15. Zero reference line (CardDetailPage.tsx:151)

```tsx
<line x1={0} y1={zeroY} x2={IW} y2={zeroY}
  stroke="rgba(255,255,255,0.18)" strokeWidth={1} strokeDasharray="4 3" />
```

Note: This rgba() exists in the original source. New code should use color-mix() per Test 1 v2.

---

## 16. buildExtPoints — raw price → ChartPoint (CardDetailPage.tsx:31–41)

```ts
function buildExtPoints(data: PricePoint[], priceKey: 'tcg_price' | 'ebay_price'): ExtPoint[] {
  const filtered = data.filter(d => d[priceKey] != null && (d[priceKey] as number) > 0)
  if (filtered.length === 0) return []
  const baseline = filtered[0][priceKey] as number
  return filtered.map(d => ({
    time: new Date(d.date).getTime(),
    raw: d[priceKey] as number,
    pct: ((d[priceKey] as number - baseline) / baseline) * 100,
    date: d.date,
  }))
}
```

---

---

## PIPELINE WARNING — batch_get data fidelity is incomplete

**Confirmed missing from batch_get output:** `dashPattern` (strokeDasharray).
**Suspected missing class:** any non-fill/stroke SVG paint attribute — the gap is
not limited to dashPattern. batch_get reliably returns fill color, stroke color,
and stroke thickness. It may silently drop:
- `dashPattern` / strokeDasharray
- `strokeLinecap` / `strokeLinejoin`
- `opacity` on strokes
- Any other paint attribute beyond fill+stroke color+thickness

**Rule when generating code from a Pencil design:**
- batch_get = authoritative for **structure, position, size, fill color, stroke color/thickness**
- Cheat sheet = authoritative for **stroke style (dash, cap, join), opacity, and all other paint attributes**
- Never trust batch_get output alone. Always cross-reference cheat sheet patterns.
  A batch_get result that looks complete may be silently missing critical style data.

---

## Summary: do NOT rename or replicate these

| Name | File | What it does |
|---|---|---|
| `ChartPoint` | chartUtils.ts | `{ time, pct }` — the canonical point type |
| `ChartSegment` | chartUtils.ts | `{ type: 'solid'\|'gap', points }` |
| `splitIntoSegments` | chartUtils.ts | Splits on >24h gaps |
| `buildAreaPath` | CardDetailPage.tsx | M/L path for gradient fill under line |
| `buildExtPoints` | CardDetailPage.tsx | Converts raw PricePoint[] to ExtPoint[] |
| `xScale` | CardDetailPage.tsx | time → inner x pixel (no PAD offset) |
| `yOf` | CardDetailPage.tsx | pct → inner y pixel |
| `zeroY` | CardDetailPage.tsx | Clamped y position of the 0% baseline |
| `tcg-norm-grad` | CardDetailPage.tsx | Gold gradient id |
| `ebay-norm-grad` | CardDetailPage.tsx | Breakout gradient id |
