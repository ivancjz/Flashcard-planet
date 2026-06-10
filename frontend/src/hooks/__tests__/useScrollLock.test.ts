/**
 * useScrollLock — body scroll-lock for open modals/drawers.
 * Closes the one residual gap from the 2026-05-08 modal a11y audit
 * (TASK-T03 item 1): role/aria/focus-trap/Esc were already shipped; scroll
 * lock was not. Each test fully unmounts so the module-level ref count
 * returns to 0 before the next test.
 */
import { describe, it, expect, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useScrollLock } from '../useScrollLock'

afterEach(() => {
  document.body.style.overflow = ''
})

describe('useScrollLock', () => {
  it('locks body overflow while active and restores on unmount', () => {
    const { unmount } = renderHook(() => useScrollLock(true))
    expect(document.body.style.overflow).toBe('hidden')
    unmount()
    expect(document.body.style.overflow).toBe('')
  })

  it('does nothing when inactive', () => {
    const { unmount } = renderHook(() => useScrollLock(false))
    expect(document.body.style.overflow).toBe('')
    unmount()
    expect(document.body.style.overflow).toBe('')
  })

  it('reference-counts stacked locks (stays locked until the last releases)', () => {
    const a = renderHook(() => useScrollLock(true))
    const b = renderHook(() => useScrollLock(true))
    expect(document.body.style.overflow).toBe('hidden')
    a.unmount()
    expect(document.body.style.overflow).toBe('hidden')
    b.unmount()
    expect(document.body.style.overflow).toBe('')
  })

  it('restores a pre-existing inline overflow value rather than clearing it', () => {
    document.body.style.overflow = 'scroll'
    const { unmount } = renderHook(() => useScrollLock(true))
    expect(document.body.style.overflow).toBe('hidden')
    unmount()
    expect(document.body.style.overflow).toBe('scroll')
  })

  it('locks and unlocks as active toggles on a mounted hook', () => {
    const { rerender, unmount } = renderHook(
      ({ active }) => useScrollLock(active),
      { initialProps: { active: false } },
    )
    expect(document.body.style.overflow).toBe('')
    rerender({ active: true })
    expect(document.body.style.overflow).toBe('hidden')
    rerender({ active: false })
    expect(document.body.style.overflow).toBe('')
    unmount()
  })
})
