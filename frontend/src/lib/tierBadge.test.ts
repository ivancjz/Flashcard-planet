import { describe, it, expect } from 'vitest'
import { tierBadge } from './tierBadge'

describe('tierBadge', () => {
  it("returns PRO style for tier='pro'", () => {
    const b = tierBadge('pro')
    expect(b).not.toBeNull()
    expect(b!.label).toBe('PRO')
    expect(b!.color).toBe('var(--gold)')
    expect(b!.borderColor).toBe('var(--border-gold-soft)')
  })

  it("returns PLUS style for tier='plus' (Lesson 13 regression guard)", () => {
    const b = tierBadge('plus')
    expect(b).not.toBeNull()
    expect(b!.label).toBe('PLUS')
    expect(b!.color).toBe('var(--plus)')
    expect(b!.borderColor).toBe('var(--border-plus-soft)')
  })

  it("returns null for tier='free'", () => {
    expect(tierBadge('free')).toBeNull()
  })
})
