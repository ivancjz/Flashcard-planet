import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import DailyReportDetailPage from './DailyReportDetailPage'
import { fetchDailyMarketReportByDate } from '../api/api'
import type { DailyMarketReport } from '../types/api'

vi.mock('../api/api', () => ({
  fetchDailyMarketReportByDate: vi.fn(),
}))

vi.mock('../components/NavBar', () => ({
  default: () => <nav aria-label="Main navigation" />,
}))

function makeReport(): DailyMarketReport {
  return {
    id: 'report-2026-07-21',
    report_date: '2026-07-21',
    generated_at: '2026-07-21T10:00:00Z',
    status: 'published',
    title: 'Flashcard Planet Daily - 2026-07-21',
    market_sentiment: 'bullish',
    confidence_label: 'high',
    summary: 'Pokemon cards led a broad but evidence-backed market advance.',
    overview: {
      generated_at: '2026-07-21T10:00:00Z',
      market_sentiment: 'bullish',
      confidence_label: 'high',
      indexes: [
        {
          game: 'pokemon',
          label: 'Pokemon Market',
          change_pct: '4.25',
          direction: 'up',
          observed_assets: 18,
          current_assets: 22,
          confidence_label: 'high',
        },
      ],
      top_movers: [
        {
          asset_id: 'asset-charizard',
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
        { label: 'BREAKOUT', count: 3, average_confidence: '88.00' },
      ],
      commentary: 'Raw Pokemon price series produced the strongest verified move.',
      evidence: ['market_segment=raw'],
    },
    catalysts: [],
    evidence: ['market_segment=raw', 'active price source: sample_seed'],
  }
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/reports/2026-07-21']}>
      <Routes>
        <Route path="/reports/:reportDate" element={<DailyReportDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('DailyReportDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('announces the report loading state', () => {
    vi.mocked(fetchDailyMarketReportByDate).mockReturnValue(new Promise(() => {}))

    renderPage()

    const status = screen.getByRole('status')
    expect(status.getAttribute('aria-busy')).toBe('true')
    expect(status.textContent).toContain('Loading daily report')
  })

  it('renders the full persisted report and its evidence', async () => {
    vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(makeReport())

    renderPage()

    expect(await screen.findByRole('heading', { name: 'Flashcard Planet Daily - 2026-07-21' })).toBeTruthy()
    expect(screen.getByText('Jul 21, 2026')).toBeTruthy()
    expect(screen.getByText('Pokemon cards led a broad but evidence-backed market advance.')).toBeTruthy()
    expect(screen.getByText('active price source: sample_seed')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'All daily reports' }).getAttribute('href')).toBe('/reports')
    expect(fetchDailyMarketReportByDate).toHaveBeenCalledWith('2026-07-21')
  })

  it('renders indexes, movers, and signal summary', async () => {
    vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(makeReport())

    renderPage()

    const indexes = await screen.findByRole('region', { name: 'Market Indexes' })
    expect(within(indexes).getByText('Pokemon Market')).toBeTruthy()
    expect(within(indexes).getByText('+4.25%')).toBeTruthy()

    const movers = screen.getByRole('region', { name: 'Top Movers' })
    expect(within(movers).getByRole('link', { name: 'Charizard' }).getAttribute('href')).toBe('/market/asset-charizard')
    expect(within(movers).getByText('$120.00')).toBeTruthy()
    expect(within(movers).getByText('+20.00%')).toBeTruthy()

    const signals = screen.getByRole('region', { name: 'Signal Summary' })
    expect(within(signals).getByText('Breakout')).toBeTruthy()
    expect(within(signals).getByText('3 signals')).toBeTruthy()
    expect(within(signals).getByText('88.00% confidence')).toBeTruthy()
  })

  it('does not turn unavailable signal confidence into a numeric measurement', async () => {
    const report = makeReport()
    report.overview.signal_summary = [
      { label: 'WATCH', count: 2, average_confidence: null },
    ]
    vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(report)

    renderPage()

    const signals = await screen.findByRole('region', { name: 'Signal Summary' })
    expect(within(signals).getByText('Confidence unavailable')).toBeTruthy()
    expect(within(signals).queryByText('0.00% confidence')).toBeNull()
  })

  it('renders a missing report state', async () => {
    vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(null)

    renderPage()

    expect(await screen.findByRole('heading', { name: 'Daily report not found' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Return to daily reports' }).getAttribute('href')).toBe('/reports')
  })

  it('renders a request error state', async () => {
    vi.mocked(fetchDailyMarketReportByDate).mockRejectedValue(new Error('network error'))

    renderPage()

    expect(await screen.findByText('This daily report is temporarily unavailable.')).toBeTruthy()
  })

  it('labels empty report subsections instead of leaving blank space', async () => {
    const report = makeReport()
    report.overview.indexes = []
    report.overview.top_movers = []
    report.overview.signal_summary = []
    vi.mocked(fetchDailyMarketReportByDate).mockResolvedValue(report)

    renderPage()

    expect(await screen.findByText('No comparable market indexes were captured.')).toBeTruthy()
    expect(screen.getByText('No qualifying movers were captured.')).toBeTruthy()
    expect(screen.getByText('No active signals were captured.')).toBeTruthy()
  })
})
