export interface ChartPoint {
  time: number  // ms timestamp
  pct: number   // normalized % change from baseline
}

export interface ChartSegment {
  type: 'solid' | 'gap'
  points: ChartPoint[]
}

const GAP_THRESHOLD_MS = 24 * 60 * 60 * 1000

export function splitIntoSegments(points: ChartPoint[]): ChartSegment[] {
  if (points.length === 0) return []
  if (points.length === 1) return [{ type: 'solid', points: [...points] }]

  const segments: ChartSegment[] = []
  let currentRun: ChartPoint[] = [points[0]]

  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1]
    const curr = points[i]

    if (curr.time - prev.time > GAP_THRESHOLD_MS) {
      segments.push({ type: 'solid', points: [...currentRun] })
      segments.push({ type: 'gap', points: [prev, curr] })
      currentRun = [curr]
    } else {
      currentRun.push(curr)
    }
  }

  if (currentRun.length > 0) {
    segments.push({ type: 'solid', points: [...currentRun] })
  }

  return segments
}

/**
 * Returns the start of the latest continuous run (no gaps >24h back to the last point).
 * Returns null when all data is already continuous (no label needed).
 */
export function findContinuousStart(points: ChartPoint[]): Date | null {
  if (points.length < 2) return null

  let runStart = points.length - 1
  for (let i = points.length - 1; i > 0; i--) {
    if (points[i].time - points[i - 1].time > GAP_THRESHOLD_MS) break
    runStart = i - 1
  }

  if (runStart === 0 || runStart === points.length - 1) return null
  return new Date(points[runStart].time)
}
