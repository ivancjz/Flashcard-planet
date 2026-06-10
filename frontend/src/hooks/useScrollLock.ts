import { useEffect } from 'react'

/**
 * Lock body scroll while a modal/drawer is open, so the page behind it
 * doesn't scroll (and mobile rubber-banding is suppressed). Companion to
 * useFocusTrap — same `open` trigger, separate concern.
 *
 * Reference-counted: if two locks are active at once (stacked surfaces),
 * the body stays locked until the last one releases. The pre-lock overflow
 * value is captured on the first lock and restored on the last release, so
 * an inline body overflow set elsewhere survives a lock cycle.
 */
let lockCount = 0
let savedOverflow = ''

export function useScrollLock(active: boolean) {
  useEffect(() => {
    if (!active) return
    if (lockCount === 0) {
      savedOverflow = document.body.style.overflow
      document.body.style.overflow = 'hidden'
    }
    lockCount++
    return () => {
      lockCount--
      if (lockCount === 0) {
        document.body.style.overflow = savedOverflow
      }
    }
  }, [active])
}
