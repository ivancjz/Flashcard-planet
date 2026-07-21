import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import DailyReportsPage from './DailyReportsPage'
import { fetchDailyMarketReports } from '../api/api'
import type { DailyMarketReport } from '../types/api'

vi.mock('../api/api', () => ({
  fetchDailyMarketReports: vi.fn(),
}))

vi.mock('../components/NavBar', () => ({
  default: () => <nav aria-label="Main navigation" />,
}))

function makeReport(reportDate: string, title: string): DailyMarketReport {
  return {
    id: `report-${reportDate}`,
    report_date: reportDate,
    generated_at: `${reportDate}T10:00:00Z`,
    status: 'published',
    title,
    market_sentiment: 'bullish',
    confidence_label: 'medium',
    summary: `Market summary for ${reportDate}.`,
    overview: {
      generated_at: `${reportDate}T10:00:00Z`,
      market_sentiment: 'bullish',
      confidence_label: 'medium',
      indexes: [],
      top_movers: [],
      signal_summary: [],
      commentary: `Market summary for ${reportDate}.`,
      evidence: ['market_segment=raw'],
    },
    catalysts: [],
    evidence: ['market_segment=raw'],
  }
}

function renderPage() {
  return render(
    <MemoryRouter>
      <DailyReportsPage />
    </MemoryRouter>,
  )
}

describe('DailyReportsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('announces the archive loading state', () => {
    vi.mocked(fetchDailyMarketReports).mockReturnValue(new Promise(() => {}))

    renderPage()

    const status = screen.getByRole('status')
    expect(status.getAttribute('aria-busy')).toBe('true')
    expect(status.textContent).toContain('Loading daily reports')
    expect(screen.getAllByTestId('daily-report-skeleton')).toHaveLength(3)
  })

  it('renders reports as links to their dated pages', async () => {
    vi.mocked(fetchDailyMarketReports).mockResolvedValue({
      reports: [
        makeReport('2026-07-21', 'Flashcard Planet Daily - 2026-07-21'),
        makeReport('2026-07-20', 'Flashcard Planet Daily - 2026-07-20'),
      ],
      total: 2,
      limit: 30,
      offset: 0,
    })

    renderPage()

    const newest = await screen.findByRole('link', { name: /Flashcard Planet Daily - 2026-07-21/ })
    expect(newest.getAttribute('href')).toBe('/reports/2026-07-21')
    expect(screen.getByText('Jul 21, 2026')).toBeTruthy()
    expect(screen.getAllByText('Bullish')).toHaveLength(2)
    expect(screen.queryByRole('button', { name: 'Load older reports' })).toBeNull()
  })

  it('renders a stable empty archive state', async () => {
    vi.mocked(fetchDailyMarketReports).mockResolvedValue({
      reports: [],
      total: 0,
      limit: 30,
      offset: 0,
    })

    renderPage()

    expect(await screen.findByText('No daily reports have been published yet.')).toBeTruthy()
  })

  it('renders an archive request error', async () => {
    vi.mocked(fetchDailyMarketReports).mockRejectedValue(new Error('network error'))

    renderPage()

    expect(await screen.findByText('Daily report history is unavailable.')).toBeTruthy()
  })

  it('appends older reports without replacing the current archive', async () => {
    vi.mocked(fetchDailyMarketReports)
      .mockResolvedValueOnce({
        reports: [makeReport('2026-07-21', 'Flashcard Planet Daily - 2026-07-21')],
        total: 2,
        limit: 30,
        offset: 0,
      })
      .mockResolvedValueOnce({
        reports: [makeReport('2026-07-20', 'Flashcard Planet Daily - 2026-07-20')],
        total: 2,
        limit: 30,
        offset: 1,
      })

    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Load older reports' }))

    expect(await screen.findByText('Flashcard Planet Daily - 2026-07-20')).toBeTruthy()
    expect(screen.getByText('Flashcard Planet Daily - 2026-07-21')).toBeTruthy()
    expect(fetchDailyMarketReports).toHaveBeenNthCalledWith(2, { limit: 30, offset: 1 })
    expect(screen.queryByRole('button', { name: 'Load older reports' })).toBeNull()
    expect(screen.getByRole('status').textContent).toBe('1 older report loaded.')
  })

  it('announces pagination progress in a live status region', async () => {
    vi.mocked(fetchDailyMarketReports)
      .mockResolvedValueOnce({
        reports: [makeReport('2026-07-21', 'Flashcard Planet Daily - 2026-07-21')],
        total: 2,
        limit: 30,
        offset: 0,
      })
      .mockReturnValueOnce(new Promise(() => {}))

    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Load older reports' }))

    const status = screen.getByRole('status')
    expect(status.getAttribute('aria-live')).toBe('polite')
    expect(status.textContent).toBe('Loading older reports...')
  })
})
