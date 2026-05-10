import { describe, test, expect } from 'vitest'
import { splitIntoSegments, findContinuousStart } from './chartUtils'

const HOUR = 60 * 60 * 1000
const DAY = 24 * HOUR

describe('splitIntoSegments', () => {
  test('continuous data returns single solid segment', () => {
    const points = [
      { time: 1000, pct: 0 },
      { time: 1000 + HOUR, pct: 5 },
      { time: 1000 + 2 * HOUR, pct: 10 },
    ]
    const result = splitIntoSegments(points)
    expect(result).toHaveLength(1)
    expect(result[0].type).toBe('solid')
    expect(result[0].points).toHaveLength(3)
  })

  test('one gap splits into solid + gap + solid', () => {
    const points = [
      { time: 1000, pct: 0 },
      { time: 1000 + 2 * DAY, pct: 10 },
      { time: 1000 + 2 * DAY + HOUR, pct: 12 },
    ]
    const result = splitIntoSegments(points)
    expect(result).toHaveLength(3)
    expect(result[0].type).toBe('solid')
    expect(result[1].type).toBe('gap')
    expect(result[2].type).toBe('solid')
  })

  test('gap segment contains exactly the two boundary points', () => {
    const points = [
      { time: 1000, pct: 0 },
      { time: 1000 + 2 * DAY, pct: 10 },
      { time: 1000 + 2 * DAY + HOUR, pct: 12 },
    ]
    const result = splitIntoSegments(points)
    expect(result[1].points).toHaveLength(2)
    expect(result[1].points[0]).toEqual(points[0])
    expect(result[1].points[1]).toEqual(points[1])
  })

  test('gap exactly at 24h is still solid (uses >)', () => {
    const points = [
      { time: 0, pct: 0 },
      { time: DAY, pct: 5 },
    ]
    const result = splitIntoSegments(points)
    expect(result).toHaveLength(1)
    expect(result[0].type).toBe('solid')
  })

  test('gap just over 24h produces solid + gap + solid', () => {
    const points = [
      { time: 0, pct: 0 },
      { time: DAY + 1, pct: 5 },
    ]
    const result = splitIntoSegments(points)
    expect(result).toHaveLength(3)
    expect(result[0].type).toBe('solid')
    expect(result[1].type).toBe('gap')
    expect(result[2].type).toBe('solid')
  })

  test('empty input', () => {
    expect(splitIntoSegments([])).toEqual([])
  })

  test('single point returns one solid segment', () => {
    const result = splitIntoSegments([{ time: 1000, pct: 0 }])
    expect(result).toHaveLength(1)
    expect(result[0].type).toBe('solid')
    expect(result[0].points).toHaveLength(1)
  })

  test('all sparse — every pair is a gap', () => {
    const points = [
      { time: 0, pct: 0 },
      { time: 2 * DAY, pct: 10 },
      { time: 4 * DAY, pct: 20 },
    ]
    const result = splitIntoSegments(points)
    // solid(1pt) + gap + solid(1pt) + gap + solid(1pt)...
    // Actually: solid([p0]), gap([p0,p1]), solid([p1]), gap([p1,p2]), solid([p2])
    const types = result.map(s => s.type)
    expect(types).toEqual(['solid', 'gap', 'solid', 'gap', 'solid'])
  })
})

describe('findContinuousStart', () => {
  test('all continuous returns null', () => {
    const points = [
      { time: 1000, pct: 0 },
      { time: 1000 + HOUR, pct: 5 },
    ]
    expect(findContinuousStart(points)).toBeNull()
  })

  test('gap at start returns first post-gap point', () => {
    const points = [
      { time: 1000, pct: 0 },
      { time: 1000 + 5 * DAY, pct: 5 },
      { time: 1000 + 5 * DAY + HOUR, pct: 6 },
      { time: 1000 + 5 * DAY + 2 * HOUR, pct: 7 },
    ]
    const result = findContinuousStart(points)
    expect(result).not.toBeNull()
    expect(result?.getTime()).toBe(1000 + 5 * DAY)
  })

  test('single point returns null', () => {
    expect(findContinuousStart([{ time: 1000, pct: 0 }])).toBeNull()
  })

  test('empty input returns null', () => {
    expect(findContinuousStart([])).toBeNull()
  })

  test('isolated tail point (gap before last point) returns null', () => {
    // p0 → p1 (1h, continuous) → p2 (2-day gap, isolated tail)
    // Latest run is just p2 alone — not a real continuous run
    const points = [
      { time: 0, pct: 0 },
      { time: HOUR, pct: 1 },
      { time: HOUR + 2 * DAY, pct: 5 },
    ]
    expect(findContinuousStart(points)).toBeNull()
  })

  test('all sparse returns null', () => {
    const points = [
      { time: 0, pct: 0 },
      { time: 2 * DAY, pct: 10 },
      { time: 4 * DAY, pct: 20 },
    ]
    expect(findContinuousStart(points)).toBeNull()
  })

  test('continuous run of ≥2 points at end returns run start', () => {
    // p0 (old) → big gap → p1, p2, p3 (continuous)
    const points = [
      { time: 0, pct: 0 },
      { time: 5 * DAY, pct: 5 },
      { time: 5 * DAY + HOUR, pct: 6 },
      { time: 5 * DAY + 2 * HOUR, pct: 7 },
    ]
    const result = findContinuousStart(points)
    expect(result?.getTime()).toBe(5 * DAY)
  })
})
