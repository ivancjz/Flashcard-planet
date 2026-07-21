import { describe, expect, it, vi, beforeEach } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import DashboardPage from './DashboardPage'
import { fetchCards, fetchCatalysts, fetchLatestDailyMarketReport, fetchMarketOverview, fetchStats, fetchTicker } from '../api/api'
import type { Catalyst, CatalystListResponse } from '../types/api'

const gameCommitProbe = vi.hoisted(() => vi.fn())

vi.mock('../api/api', () => ({
  fetchStats: vi.fn(),
  fetchTicker: vi.fn(),
  fetchCards: vi.fn(),
  fetchSetOptions: vi.fn(),
  fetchMarketOverview: vi.fn(),
  fetchLatestDailyMarketReport: vi.fn(),
  fetchCatalysts: vi.fn(),
}))

vi.mock('../components/NavBar', () => ({ default: () => <nav aria-label="Main navigation" /> }))
vi.mock('../components/TickerBar', () => ({ default: () => <div data-testid="ticker-bar" /> }))
vi.mock('../components/GameSwitcher', async () => {
  const { useLayoutEffect } = await import('react')

  function MockGameSwitcher({ activeGame, onGameChange }: { activeGame: string; onGameChange: (game: string) => void }) {
    useLayoutEffect(() => {
      gameCommitProbe(activeGame, document.body.textContent ?? '')
    }, [activeGame])

    return (
      <div data-testid="game-switcher">
        <span>{activeGame}</span>
        <button type="button" onClick={() => onGameChange('yugioh')}>Select Yu-Gi-Oh</button>
      </div>
    )
  }

  return { default: MockGameSwitcher }
})
vi.mock('../components/FilterDrawer', () => ({ default: () => null }))
vi.mock('../components/CardGrid', () => ({
  default: ({ cards, loading }: { cards: unknown[]; loading?: boolean }) => (
    <div data-testid="card-grid">{loading ? 'loading cards' : `${cards.length} cards`}</div>
  ),
}))
vi.mock('../components/ProGate', () => ({ default: ({ children }: { children: React.ReactNode }) => <>{children}</> }))

const pokemonCatalyst: Catalyst = {
  id: 'pokemon-regionals-2026',
  event_date: '2026-08-10',
  active_until: '2026-08-12',
  event_type: 'REGIONAL_CHAMPIONSHIP',
  description: 'Pokemon regional championship registration opens.',
  source_url: 'https://example.com/pokemon-regionals',
  affected_games: ['pokemon'],
  affected_asset_ids: [],
  affected_set_ids: [],
  expected_window_days: 3,
  impact_score: 72,
  impact_label: 'medium',
  confidence_score: '84.00',
  confidence_label: 'high',
  status: 'upcoming',
  verified_at: '2026-07-22T01:00:00Z',
}

function catalystPage(catalysts: Catalyst[]): CatalystListResponse {
  return {
    catalysts,
    total: catalysts.length,
    limit: 3,
    offset: 0,
    as_of: '2026-07-22T01:00:00Z',
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(resolvePromise => {
    resolve = resolvePromise
  })
  return { promise, resolve }
}

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
    vi.mocked(fetchCatalysts).mockResolvedValue(catalystPage([pokemonCatalyst]))
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
      catalysts: [],
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
    expect(within(report).getByRole('link', { name: 'Read full report' }).getAttribute('href')).toBe('/reports/2026-07-21')
    expect(fetchLatestDailyMarketReport).toHaveBeenCalledTimes(1)
  })

  it('shows a neutral state when no daily report has been generated', async () => {
    vi.mocked(fetchLatestDailyMarketReport).mockResolvedValueOnce(null)

    renderDashboard()

    expect(await screen.findByText("Today's report has not been generated yet.")).toBeTruthy()
    expect(screen.queryByRole('link', { name: 'Read full report' })).toBeNull()
  })

  it('announces the pending daily report as a live loading region', async () => {
    vi.mocked(fetchLatestDailyMarketReport).mockReturnValueOnce(new Promise(() => {}))

    renderDashboard()

    const report = await screen.findByRole('region', { name: 'Flashcard Planet Daily' })
    expect(report.getAttribute('aria-busy')).toBe('true')
    expect(report.getAttribute('aria-live')).toBe('polite')
    expect(within(report).getByText('Loading the latest market brief...')).toBeTruthy()
    expect(screen.queryByRole('link', { name: 'Read full report' })).toBeNull()
  })

  it('shows an unavailable state when the daily report request fails', async () => {
    vi.mocked(fetchLatestDailyMarketReport).mockRejectedValueOnce(new Error('network error'))

    renderDashboard()

    expect(await screen.findByText('Daily report unavailable.')).toBeTruthy()
    expect(screen.queryByRole('link', { name: 'Read full report' })).toBeNull()
  })

  it('requests Pokemon catalysts and renders the returned event', async () => {
    renderDashboard()

    const panel = await screen.findByRole('region', { name: 'Market Catalysts' })
    expect(within(panel).getByText('Pokemon regional championship registration opens.')).toBeTruthy()
    expect(fetchCatalysts).toHaveBeenCalledWith({
      status: ['active', 'upcoming'],
      game: 'pokemon',
      limit: 3,
      offset: 0,
    })
  })

  it('requests catalysts again when the active game changes', async () => {
    renderDashboard()
    await screen.findByText('Pokemon regional championship registration opens.')

    fireEvent.click(screen.getByRole('button', { name: 'Select Yu-Gi-Oh' }))

    await waitFor(() => expect(fetchCatalysts).toHaveBeenCalledTimes(2))
    expect(fetchCatalysts).toHaveBeenNthCalledWith(2, {
      status: ['active', 'upcoming'],
      game: 'yugioh',
      limit: 3,
      offset: 0,
    })
  })

  it('clears the previous game catalysts in the same commit as a game switch', async () => {
    const pendingYugiohRequest = new Promise<CatalystListResponse>(() => {})
    vi.mocked(fetchCatalysts)
      .mockResolvedValueOnce(catalystPage([pokemonCatalyst]))
      .mockReturnValueOnce(pendingYugiohRequest)

    renderDashboard()
    await screen.findByText('Pokemon regional championship registration opens.')

    fireEvent.click(screen.getByRole('button', { name: 'Select Yu-Gi-Oh' }))

    const yugiohCommit = gameCommitProbe.mock.calls.find(([game]) => game === 'yugioh')
    const yugiohCommitText = yugiohCommit?.[1] ?? ''
    expect(yugiohCommitText).not.toContain('Pokemon regional championship registration opens.')
    expect(yugiohCommitText).toContain('Loading market catalysts...')
    expect(screen.queryByText('Pokemon regional championship registration opens.')).toBeNull()
    expect(screen.getByText('Loading market catalysts...')).toBeTruthy()
  })

  it('ignores a stale Pokemon response after switching to Yugioh', async () => {
    const pokemonRequest = deferred<CatalystListResponse>()
    const yugiohRequest = deferred<CatalystListResponse>()
    const stalePokemonCatalyst = {
      ...pokemonCatalyst,
      description: 'Late Pokemon catalyst response.',
    }
    const yugiohCatalyst = {
      ...pokemonCatalyst,
      id: 'yugioh-championship-2026',
      affected_games: ['yugioh'],
      description: 'Current Yugioh championship event.',
    }
    vi.mocked(fetchCatalysts).mockImplementation(params => (
      params?.game === 'pokemon' ? pokemonRequest.promise : yugiohRequest.promise
    ))

    renderDashboard()
    fireEvent.click(screen.getByRole('button', { name: 'Select Yu-Gi-Oh' }))
    await waitFor(() => expect(fetchCatalysts).toHaveBeenCalledTimes(2))

    await act(async () => {
      yugiohRequest.resolve(catalystPage([yugiohCatalyst]))
      await Promise.resolve()
    })
    expect(await screen.findByText('Current Yugioh championship event.')).toBeTruthy()

    await act(async () => {
      pokemonRequest.resolve(catalystPage([stalePokemonCatalyst]))
      await Promise.resolve()
    })
    expect(screen.queryByText('Late Pokemon catalyst response.')).toBeNull()
    expect(screen.getByText('Current Yugioh championship event.')).toBeTruthy()
  })

  it('isolates catalyst request failures from the other dashboard sections', async () => {
    vi.mocked(fetchCatalysts).mockRejectedValueOnce(new Error('network error'))

    renderDashboard()

    expect(await screen.findByText('Market catalysts unavailable.')).toBeTruthy()
    expect(screen.getByRole('region', { name: 'Flashcard Planet Daily' })).toBeTruthy()
    expect(await screen.findByRole('region', { name: 'Market Overview' })).toBeTruthy()
    expect(screen.getByTestId('card-grid')).toBeTruthy()
  })
})
