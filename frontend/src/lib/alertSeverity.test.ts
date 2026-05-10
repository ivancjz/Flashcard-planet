import { describe, it, expect } from 'vitest'
import { alertSeverityStyles } from './alertSeverity'

describe('alertSeverityStyles', () => {
  it("returns --severity-high + --tint-danger for 'high'", () => {
    const s = alertSeverityStyles('high')
    expect(s.accent).toBe('var(--severity-high)')
    expect(s.tint).toBe('var(--tint-danger)')
  })

  it("returns --severity-med + --tint-severity-med for 'medium'", () => {
    const s = alertSeverityStyles('medium')
    expect(s.accent).toBe('var(--severity-med)')
    expect(s.tint).toBe('var(--tint-severity-med)')
  })

  it("returns --severity-low + --tint-severity-low for 'low'", () => {
    const s = alertSeverityStyles('low')
    expect(s.accent).toBe('var(--severity-low)')
    expect(s.tint).toBe('var(--tint-severity-low)')
  })

  it('returns full token strings (no runtime concatenation)', () => {
    // Regression guard for AlertsPage.tsx:100 bug: any value that
    // contains "var(" and ends with a separate alpha suffix at runtime
    // produces invalid CSS. The helper must return ONLY tokens or hex.
    for (const sev of ['high', 'medium', 'low'] as const) {
      const { accent, tint } = alertSeverityStyles(sev)
      expect(accent).toMatch(/^var\(--/)
      expect(tint).toMatch(/^var\(--/)
    }
  })
})
