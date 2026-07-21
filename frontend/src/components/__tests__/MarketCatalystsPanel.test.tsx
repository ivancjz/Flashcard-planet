import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import MarketCatalystsPanel from '../MarketCatalystsPanel'
import type { Catalyst } from '../../types/api'

const baseCatalyst: Catalyst = {
  id: 'pokemon-reprint-2026',
  event_date: '2026-08-01',
  active_until: '2026-08-15',
  event_type: 'REPRINT',
  description: 'A verified Pokemon reprint window.',
  source_url: 'https://example.com/reprint',
  affected_games: ['pokemon'],
  affected_asset_ids: [],
  affected_set_ids: ['base1'],
  expected_window_days: null,
  impact_score: null,
  impact_label: 'unscored',
  confidence_score: null,
  confidence_label: 'insufficient_data',
  status: 'active',
  verified_at: '2026-07-22T01:00:00Z',
}

function catalyst(overrides: Partial<Catalyst> = {}): Catalyst {
  return { ...baseCatalyst, ...overrides }
}

describe('MarketCatalystsPanel', () => {
  it('renders a stable unavailable live region', () => {
    render(<MarketCatalystsPanel catalysts={undefined} unavailable />)

    const panel = screen.getByRole('region', { name: 'Market Catalysts' })
    expect(panel.getAttribute('aria-live')).toBe('polite')
    expect(panel.getAttribute('aria-busy')).toBeNull()
    expect(within(panel).getByText('Market catalysts unavailable.')).toBeTruthy()
  })

  it('announces loading with a busy live region', () => {
    render(<MarketCatalystsPanel catalysts={undefined} unavailable={false} />)

    const panel = screen.getByRole('region', { name: 'Market Catalysts' })
    expect(panel.getAttribute('aria-live')).toBe('polite')
    expect(panel.getAttribute('aria-busy')).toBe('true')
    expect(within(panel).getByText('Loading market catalysts...')).toBeTruthy()
  })

  it('renders the exact neutral copy when no verified catalysts are returned', () => {
    render(<MarketCatalystsPanel catalysts={[]} unavailable={false} />)

    expect(screen.getByText('No verified catalysts are active or upcoming for this market.')).toBeTruthy()
  })

  it('formats active and upcoming catalyst rows safely', () => {
    render(
      <MarketCatalystsPanel
        unavailable={false}
        catalysts={[
          baseCatalyst,
          catalyst({
            id: 'community-festival-2026',
            event_date: '2026-08-01T00:30:00+14:00',
            event_type: 'COMMUNITY_FESTIVAL',
            description: 'A verified community festival is scheduled.',
            source_url: 'https://example.com/festival',
            impact_score: 88,
            impact_label: 'high',
            confidence_score: '91.50',
            confidence_label: 'high',
            status: 'upcoming',
          }),
        ]}
      />,
    )

    const panel = screen.getByRole('region', { name: 'Market Catalysts' })
    expect(within(panel).getByText('Active')).toBeTruthy()
    expect(within(panel).getByText('Upcoming')).toBeTruthy()
    expect(within(panel).getByText('Community Festival')).toBeTruthy()
    expect(within(panel).getByText('Jul 31, 2026')).toBeTruthy()
    expect(within(panel).getByText('Impact: Unscored')).toBeTruthy()
    expect(within(panel).getByText('Confidence: Insufficient evidence')).toBeTruthy()
    expect(within(panel).getByText('Impact: High (88)')).toBeTruthy()
    expect(within(panel).getByText('Confidence: High (91.50%)')).toBeTruthy()

    const evidenceLinks = within(panel).getAllByText('View evidence')
    expect(evidenceLinks).toHaveLength(2)
    expect(evidenceLinks[1].getAttribute('href')).toBe('https://example.com/festival')
    expect(evidenceLinks[1].getAttribute('target')).toBe('_blank')
    expect(evidenceLinks[1].getAttribute('rel')).toBe('noreferrer')
  })

  it('gives each evidence link a distinct contextual name while retaining its visible text', () => {
    const festivalDescription = 'A verified community festival is scheduled.'
    render(
      <MarketCatalystsPanel
        unavailable={false}
        catalysts={[
          baseCatalyst,
          catalyst({
            id: 'community-festival-2026',
            event_type: 'COMMUNITY_FESTIVAL',
            description: festivalDescription,
            source_url: 'https://example.com/festival',
          }),
        ]}
      />,
    )

    const reprintLink = screen.getByRole('link', {
      name: 'View evidence for Reprint: A verified Pokemon reprint window.',
    })
    const festivalLink = screen.getByRole('link', {
      name: `View evidence for Community Festival: ${festivalDescription}`,
    })
    expect(reprintLink.textContent).toBe('View evidence')
    expect(festivalLink.textContent).toBe('View evidence')
  })

  it.each([
    ['a javascript URL', 'javascript:alert(1)'],
    ['a relative URL', '/evidence/reprint'],
    ['a malformed URL', 'not a valid URL'],
  ])('renders evidence as unavailable for %s', (_case, sourceUrl) => {
    render(
      <MarketCatalystsPanel
        unavailable={false}
        catalysts={[catalyst({ source_url: sourceUrl })]}
      />,
    )

    expect(screen.queryByRole('link')).toBeNull()
    expect(screen.getByText('Evidence unavailable')).toBeTruthy()
  })

  it('shows invalid dates unchanged and omits nonfinite confidence numbers', () => {
    render(
      <MarketCatalystsPanel
        unavailable={false}
        catalysts={[
          catalyst({
            event_date: 'not-a-date',
            confidence_score: Number.POSITIVE_INFINITY,
            confidence_label: 'medium',
          }),
        ]}
      />,
    )

    expect(screen.getByText('not-a-date')).toBeTruthy()
    expect(screen.getByText('Confidence: Medium')).toBeTruthy()
    expect(screen.queryByText(/Infinity/)).toBeNull()
  })

  it('renders no more than the first three catalysts', () => {
    render(
      <MarketCatalystsPanel
        unavailable={false}
        catalysts={[1, 2, 3, 4].map(index => catalyst({
          id: `catalyst-${index}`,
          description: `Catalyst description ${index}`,
        }))}
      />,
    )

    expect(screen.getAllByText('View evidence')).toHaveLength(3)
    expect(screen.getByText('Catalyst description 3')).toBeTruthy()
    expect(screen.queryByText('Catalyst description 4')).toBeNull()
  })

  it('renders a long description in full', () => {
    const description = `Verified organizer notice ${'with additional event detail '.repeat(20)}`.trim()

    render(
      <MarketCatalystsPanel
        unavailable={false}
        catalysts={[catalyst({ description })]}
      />,
    )

    expect(screen.getByText(description).textContent).toBe(description)
  })
})
