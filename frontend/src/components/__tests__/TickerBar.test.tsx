/**
 * TickerBar — matchMedia / prefers-reduced-motion tests.
 *
 * Strategy: mock window.matchMedia before rendering, then render via React + jsdom
 * (no @testing-library/react installed in this project).
 *
 * The key invariant under test:
 *   - reducedMotion=false → .ticker-inner present (animated scroll)
 *   - reducedMotion=true  → .ticker-inner absent, ≤8 static items visible
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import React from 'react'
import * as ReactDOMClient from 'react-dom/client'
import { act } from 'react'
import TickerBar from '../TickerBar'
import type { TickerItem } from '../../types/api'

// Ten sample items — enough to verify the ≤8 cap on static branch
const ITEMS: TickerItem[] = Array.from({ length: 10 }, (_, i) => ({
  asset_id: `id-${i}`,
  name: `Card ${i}`,
  price_delta_pct: i % 2 === 0 ? 5 + i : -(3 + i),
  signal: 'IDLE' as const,
  current_price: 10 + i,
}))

function mockMatchMedia(matches: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
}

describe('TickerBar — prefers-reduced-motion', () => {
  let container: HTMLElement
  let root: ReactDOMClient.Root

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = ReactDOMClient.createRoot(container)
  })

  afterEach(() => {
    act(() => { root.unmount() })
    container.remove()
    vi.restoreAllMocks()
  })

  it('renders animated ticker (.ticker-inner) when reduced motion is OFF', () => {
    mockMatchMedia(false)
    act(() => { root.render(React.createElement(TickerBar, { items: ITEMS })) })

    const tickerInner = container.querySelector('.ticker-inner')
    expect(tickerInner).not.toBeNull()
  })

  it('renders static branch (no .ticker-inner) when reduced motion is ON', () => {
    mockMatchMedia(true)
    act(() => { root.render(React.createElement(TickerBar, { items: ITEMS })) })

    // Animated element must be absent
    const tickerInner = container.querySelector('.ticker-inner')
    expect(tickerInner).toBeNull()

    // Ticker bar itself still present
    const tickerBar = container.querySelector('.ticker-bar')
    expect(tickerBar).not.toBeNull()
  })

  it('static branch shows at most 8 items from the original list', () => {
    mockMatchMedia(true)
    act(() => { root.render(React.createElement(TickerBar, { items: ITEMS })) })

    // Static branch renders first ≤8 items inside the ticker-bar's flex child
    // Each item is a <span> with inline-flex style
    const tickerBar = container.querySelector('.ticker-bar')!
    const itemSpans = tickerBar.querySelectorAll(':scope > div > span')
    expect(itemSpans.length).toBeGreaterThan(0)
    expect(itemSpans.length).toBeLessThanOrEqual(8)
  })

  it('animated branch doubles items (required for seamless loop)', () => {
    mockMatchMedia(false)
    act(() => { root.render(React.createElement(TickerBar, { items: ITEMS })) })

    const tickerInner = container.querySelector('.ticker-inner')!
    // Each item is a <span>; doubled list = 2× ITEMS.length
    const spans = tickerInner.querySelectorAll(':scope > span')
    expect(spans.length).toBe(ITEMS.length * 2)
  })
})
