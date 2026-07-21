import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchLatestDailyMarketReport, fetchMarketOverview } from './api'

describe('fetchMarketOverview', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('requests the v2 market overview endpoint', async () => {
    const payload = {
      generated_at: '2026-07-21T10:00:00Z',
      market_sentiment: 'bullish',
      confidence_label: 'medium',
      indexes: [],
      top_movers: [],
      signal_summary: [],
      commentary: 'Market is bullish based on raw price series.',
      evidence: ['market_segment=raw'],
    }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue(payload),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchMarketOverview()

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/market/overview')
    expect(result.market_sentiment).toBe('bullish')
    expect(result.evidence).toContain('market_segment=raw')
  })
})

describe('fetchLatestDailyMarketReport', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('requests and returns the latest daily market report', async () => {
    const payload = {
      id: '11111111-1111-1111-1111-111111111111',
      report_date: '2026-07-21',
      generated_at: '2026-07-21T10:00:00Z',
      status: 'published',
      title: 'Flashcard Planet Daily',
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
      evidence: ['market_segment=raw'],
    }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue(payload),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchLatestDailyMarketReport()

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/market/daily-report/latest')
    expect(result?.title).toBe('Flashcard Planet Daily')
  })

  it('returns null when no daily market report has been generated', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }))

    await expect(fetchLatestDailyMarketReport()).resolves.toBeNull()
  })

  it('throws when the daily market report request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }))

    await expect(fetchLatestDailyMarketReport()).rejects.toThrow('daily market report fetch failed')
  })
})
