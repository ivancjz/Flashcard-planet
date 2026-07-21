import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import DashboardPage from './DashboardPage'
import { fetchCards, fetchLatestDailyMarketReport, fetchMarketOverview, fetchStats, fetchTicker } from '../api/api'

vi.mock('../api/api', () => ({
  fetchStats: vi.fn(),
  fetchTicker: vi.fn(),
  fetchCards: vi.fn(),
  fetchSetOptions: vi.fn(),
  fetchMarketOverview: vi.fn(),
  fetchLatestDailyMarketReport: vi.fn(),
}))

vi.mock('../components/NavBar', () => ({ default: () => <nav aria-label="Main navigation" /> }))
vi.mock('../components/TickerBar', () => ({ default: () => <div data-testid="ticker-bar" /> }))
vi.mock('../components/GameSwitcher', () => ({
  default: ({ activeGame }: { activeGame: string }) => <div data-testid="game-switcher">{activeGame}</div>,
}))
vi.mock('../components/FilterDrawer', () => ({ default: () => null }))
vi.mock('../components/CardGrid', () => ({
  default: ({ cards, loading }: { cards: unknown[]; loading?: boolean }) => (
    <div data-testid="card-grid">{loading ? 'loading cards' : `${cards.length} cards`}</div>
  ),
}))
vi.mock('../components/ProGate', () => ({ default: ({ children }: { children: React.ReactNode }) => <>{children}</> }))

function renderDashboard() {
  return render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>
  )
}

describe('DashboardPage market overview', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(fetchStats).mockResolvedValue({
      total_assets: 12,
      signal_counts: {
        BREAKOUT: 1,
        MOVE: 2,
        WATCH: 3,
        IDLE: 4,
        INSUFFICIENT_DATA: 0,
      },
      last_ingest_utc: null,
      next_ingest_utc: null,
      sources_active: ['sample_seed'],
    })
    vi.mocked(fetchTicker).mockResolvedValue([])
    vi.mocked(fetchCards).mockResolvedValue({ cards: [], total: 0, limit: 50, offset: 0 })
    vi.mocked(fetchLatestDailyMarketReport).mockResolvedValue({
      id: '22222222-2222-2222-2222-222222222222',
      report_date: '2026-07-21',
      generated_at: '2026-07-21T10:00:00Z',
      status: 'published',
      title: 'Flashcard Planet Daily - 2026-07-21',
      market_sentiment: 'bullish',
      confidence_label: 'medium',
      summary: 'High-end Pokemon cards led the raw market today.',
      overview: {
        generated_at: '2026-07-21T10:00:00Z',
        market_sentiment: 'bullish',
        confidence_label: 'medium',
        indexes: [],
        top_movers: [],
        signal_summary: [],
        commentary: 'High-end Pokemon cards led the raw market today.',
        evidence: ['market_segment=raw'],
      },
      evidence: ['market_segment=raw', 'active price source: sample_seed'],
    })
    vi.mocked(fetchMarketOverview).mockResolvedValue({
      generated_at: '2026-07-21T10:00:00Z',
      market_sentiment: 'bullish',
      confidence_label: 'medium',
      indexes: [
        {
          game: 'pokemon',
          label: 'Pokemon Market',
          change_pct: '12.34',
          direction: 'up',
          observed_assets: 4,
          current_assets: 6,
          confidence_label: 'medium',
        },
      ],
      top_movers: [
        {
          asset_id: '11111111-1111-1111-1111-111111111111',
          name: 'Charizard',
          game: 'pokemon',
          set_name: 'Base Set',
          latest_price: '120.00',
          previous_price: '100.00',
          percent_change: '20.00',
          absolute_change: '20.00',
          direction: 'up',
        },
      ],
      signal_summary: [
        { label: 'BREAKOUT', count: 1, average_confidence: '88.00' },
        { label: 'MOVE', count: 2, average_confidence: '70.00' },
      ],
      commentary: 'Market is bullish based on 4 raw price series.',
      evidence: ['market_segment=raw', 'active price source: sample_seed'],
    })
  })

  it('renders the v2 market overview summary', async () => {
    renderDashboard()

    expect(await screen.findByText('Market Overview')).toBeTruthy()
    const overview = screen.getByRole('region', { name: 'Market Overview' })
    expect(within(overview).getByText('Bullish')).toBeTruthy()
    expect(within(overview).getByText('Pokemon Market')).toBeTruthy()
    expect(within(overview).getByText('+12.34%')).toBeTruthy()
    expect(within(overview).getByText('Charizard')).toBeTruthy()
    expect(within(overview).getByText('+20.00%')).toBeTruthy()
    expect(within(overview).getByText('3 signals')).toBeTruthy()
    expect(within(overview).getByText('Market is bullish based on 4 raw price series.')).toBeTruthy()
    expect(fetchMarketOverview).toHaveBeenCalledTimes(1)
  })

  it('renders the latest daily market report', async () => {
    renderDashboard()

    expect(await screen.findByText('Flashcard Planet Daily - 2026-07-21')).toBeTruthy()
    const report = screen.getByRole('region', { name: 'Flashcard Planet Daily' })
    expect(within(report).getByText('Jul 21, 2026')).toBeTruthy()
    expect(within(report).getByText('Bullish')).toBeTruthy()
    expect(within(report).getByText('Medium confidence')).toBeTruthy()
    expect(within(report).getByText('High-end Pokemon cards led the raw market today.')).toBeTruthy()
    expect(within(report).getByText('market_segment=raw')).toBeTruthy()
    expect(fetchLatestDailyMarketReport).toHaveBeenCalledTimes(1)
  })

  it('shows a neutral state when no daily report has been generated', async () => {
    vi.mocked(fetchLatestDailyMarketReport).mockResolvedValueOnce(null)

    renderDashboard()

    expect(await screen.findByText("Today's report has not been generated yet.")).toBeTruthy()
  })

  it('shows an unavailable state when the daily report request fails', async () => {
    vi.mocked(fetchLatestDailyMarketReport).mockRejectedValueOnce(new Error('network error'))

    renderDashboard()

    expect(await screen.findByText('Daily report unavailable.')).toBeTruthy()
  })
})
