import { describe, it, expect } from 'vitest'
import { tierBadge } from './tierBadge'

describe('tierBadge', () => {
  it("returns PRO badge with className for tier='pro'", () => {
    const b = tierBadge('pro')
    expect(b).not.toBeNull()
    expect(b!.label).toBe('PRO')
    expect(b!.className).toBe('badge-pro')
  })

  it("returns PLUS badge with className for tier='plus' (Lesson 13 regression guard)", () => {
    const b = tierBadge('plus')
    expect(b).not.toBeNull()
    expect(b!.label).toBe('PLUS')
    expect(b!.className).toBe('badge-plus')
  })

  it("returns null for tier='free'", () => {
    expect(tierBadge('free')).toBeNull()
  })
})
