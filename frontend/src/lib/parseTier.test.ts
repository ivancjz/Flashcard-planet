import { describe, it, expect } from 'vitest'
import { parseTier } from '../contexts/UserContext'

// parseTier is the single source of truth for mapping a raw tier string
// (from /api/v1/auth/me or localStorage) to a typed Tier value.
// These tests are the regression guard for the PR #43 P1 bug:
// 'plus' was silently coerced to 'free' because ternaries only checked 'pro'.

describe('parseTier', () => {
  it("returns 'plus' when server returns tier='plus'", () => {
    expect(parseTier('plus')).toBe('plus')
  })

  it("returns 'pro' when server returns tier='pro' (regression)", () => {
    expect(parseTier('pro')).toBe('pro')
  })

  it("returns 'free' for unrecognized tier values", () => {
    expect(parseTier('enterprise')).toBe('free')
    expect(parseTier('admin')).toBe('free')
    expect(parseTier('PLUS')).toBe('free')   // case-sensitive
    expect(parseTier('PRO')).toBe('free')    // case-sensitive
  })

  it("returns 'free' for null or undefined (unauthenticated)", () => {
    expect(parseTier(null)).toBe('free')
    expect(parseTier(undefined)).toBe('free')
  })

  it("returns 'free' for explicit 'free' tier", () => {
    expect(parseTier('free')).toBe('free')
  })

  it("returns 'plus' from localStorage dev-override storage", () => {
    // Simulates the localStorage fallback path: stored === 'plus'
    expect(parseTier('plus')).toBe('plus')
  })
})
