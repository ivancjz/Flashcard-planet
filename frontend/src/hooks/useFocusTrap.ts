import { useEffect, useRef } from 'react'

/**
 * Trap keyboard focus inside a container while it's open.
 * - Tab cycles between focusable descendants.
 * - Esc calls onClose.
 * - On unmount/close, focus returns to the previously-focused element.
 *
 * Limitations (acceptable for current modal/drawer scope):
 * - Focusables are captured at open-time; descendants added later are not picked up.
 * - Single-trap only; nested modals would need a stack — not used today.
 */
export function useFocusTrap<T extends HTMLElement>(
  open: boolean,
  onClose: () => void,
) {
  const ref = useRef<T>(null)

  useEffect(() => {
    if (!open || !ref.current) return
    const root = ref.current
    const previouslyFocused = document.activeElement as HTMLElement | null

    const focusables = Array.from(
      root.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )
    )

    focusables[0]?.focus()

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
        return
      }
      if (e.key !== 'Tab' || focusables.length === 0) return
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }

    root.addEventListener('keydown', onKey)
    return () => {
      root.removeEventListener('keydown', onKey)
      previouslyFocused?.focus()
    }
  }, [open, onClose])

  return ref
}
