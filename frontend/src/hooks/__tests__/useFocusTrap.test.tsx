/**
 * useFocusTrap — regression coverage for the two highest-value a11y
 * behaviors the modal/drawer components rely on: Escape closes, and focus
 * returns to the previously-focused element on close. Hook shipped earlier
 * with no tests; this locks in the contract.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent } from '@testing-library/react'
import { useFocusTrap } from '../useFocusTrap'

function Harness({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useFocusTrap<HTMLDivElement>(open, onClose)
  if (!open) return null
  return (
    <div ref={ref} data-testid="trap">
      <button>first</button>
      <button>last</button>
    </div>
  )
}

describe('useFocusTrap', () => {
  it('calls onClose when Escape is pressed inside the trap', () => {
    const onClose = vi.fn()
    const { getByTestId } = render(<Harness open onClose={onClose} />)
    fireEvent.keyDown(getByTestId('trap'), { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('moves focus to the first focusable on open and restores it on close', () => {
    const trigger = document.createElement('button')
    document.body.appendChild(trigger)
    trigger.focus()
    expect(document.activeElement).toBe(trigger)

    const { rerender } = render(<Harness open onClose={() => {}} />)
    expect((document.activeElement as HTMLElement)?.textContent).toBe('first')

    rerender(<Harness open={false} onClose={() => {}} />)
    expect(document.activeElement).toBe(trigger)

    trigger.remove()
  })
})
