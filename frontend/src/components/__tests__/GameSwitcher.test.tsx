/**
 * GameSwitcher — keyboard/AT semantics for the "+ More" dropdown
 * (TASK-T03 item 2). "Coming soon" entries must be disabled buttons with
 * accessible names, and the toggle must expose aria-expanded state.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import GameSwitcher from '../GameSwitcher'

describe('GameSwitcher a11y', () => {
  it('exposes aria-expanded on the More toggle and flips it on click', () => {
    render(<GameSwitcher activeGame="pokemon" onGameChange={vi.fn()} />)
    const toggle = screen.getByRole('button', { name: '+ More' })
    expect(toggle.getAttribute('aria-haspopup')).toBe('true')
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
  })

  it('renders coming-soon entries as disabled buttons with accessible names', () => {
    render(<GameSwitcher activeGame="pokemon" onGameChange={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: '+ More' }))
    const mtg = screen.getByRole('button', {
      name: 'Magic: The Gathering — coming soon',
    }) as HTMLButtonElement
    expect(mtg.disabled).toBe(true)
    expect(
      (screen.getByRole('button', {
        name: 'One Piece — coming soon',
      }) as HTMLButtonElement).disabled,
    ).toBe(true)
  })
})
