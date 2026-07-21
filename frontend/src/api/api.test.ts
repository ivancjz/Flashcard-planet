import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  fetchCatalyst,
  fetchCatalysts,
  fetchDailyMarketReportByDate,
  fetchDailyMarketReports,
  fetchLatestDailyMarketReport,
  fetchMarketOverview,
} from './api'
import type { Catalyst, CatalystListResponse } from '../types/api'

const catalystFixture: Catalyst = {
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

describe('fetchCatalysts', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('serializes repeatable statuses and normalized filters', async () => {
    const payload: CatalystListResponse = {
      catalysts: [catalystFixture],
      total: 1,
      limit: 3,
      offset: 0,
      as_of: '2026-07-22T01:00:00Z',
    }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue(payload),
    })
    vi.stubGlobal('fetch', fetchMock)

    await fetchCatalysts({
      status: ['active', 'upcoming'],
      game: ' pokemon ',
      eventType: ' reprint ',
      limit: 3,
      offset: 0,
    })

    const requestUrl = new URL(fetchMock.mock.calls[0][0] as string, 'http://localhost')
    expect(requestUrl.pathname).toBe('/api/v1/market/catalysts')
    expect(requestUrl.searchParams.getAll('status')).toEqual(['active', 'upcoming'])
    expect(requestUrl.searchParams.get('game')).toBe('pokemon')
    expect(requestUrl.searchParams.get('event_type')).toBe('REPRINT')
    expect(requestUrl.searchParams.get('limit')).toBe('3')
    expect(requestUrl.searchParams.get('offset')).toBe('0')
  })

  it('uses default pagination without optional filters', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({
        catalysts: [],
        total: 0,
        limit: 20,
        offset: 0,
        as_of: '2026-07-22T01:00:00Z',
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await fetchCatalysts()

    const requestUrl = new URL(fetchMock.mock.calls[0][0] as string, 'http://localhost')
    expect(requestUrl.searchParams.get('limit')).toBe('20')
    expect(requestUrl.searchParams.get('offset')).toBe('0')
    expect(requestUrl.searchParams.has('status')).toBe(false)
    expect(requestUrl.searchParams.has('game')).toBe(false)
    expect(requestUrl.searchParams.has('event_type')).toBe(false)
  })

  it('returns catalyst values unchanged, including null scores', async () => {
    const payload: CatalystListResponse = {
      catalysts: [catalystFixture],
      total: 1,
      limit: 20,
      offset: 0,
      as_of: '2026-07-22T01:00:00Z',
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue(payload),
    }))

    const result = await fetchCatalysts()

    expect(result).toBe(payload)
    expect(result.catalysts[0]).toMatchObject({
      active_until: '2026-08-15',
      impact_label: 'unscored',
      confidence_label: 'insufficient_data',
      impact_score: null,
      confidence_score: null,
    })
  })

  it('throws when the catalyst list request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }))

    await expect(fetchCatalysts()).rejects.toThrow('catalyst list fetch failed')
  })
})

describe('fetchCatalyst', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('encodes the catalyst ID and returns the catalyst unchanged', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue(catalystFixture),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchCatalyst('pokemon/reprint 2026')

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/market/catalysts/pokemon%2Freprint%202026')
    expect(result).toBe(catalystFixture)
  })

  it('returns null when the catalyst is missing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }))

    await expect(fetchCatalyst('missing')).resolves.toBeNull()
  })

  it('throws when the catalyst request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }))

    await expect(fetchCatalyst('pokemon-reprint-2026')).rejects.toThrow('catalyst fetch failed')
  })
})

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

describe('daily market report history', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('requests a paginated report archive', async () => {
    const payload = { reports: [], total: 0, limit: 30, offset: 0 }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue(payload),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await fetchDailyMarketReports({ limit: 30, offset: 0 })

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/market/daily-report?limit=30&offset=0')
    expect(result).toEqual(payload)
  })

  it('requests a dated daily market report', async () => {
    const payload = {
      id: '11111111-1111-1111-1111-111111111111',
      report_date: '2026-07-21',
      generated_at: '2026-07-21T10:00:00Z',
      status: 'published',
      title: 'Flashcard Planet Daily - 2026-07-21',
      market_sentiment: 'bullish',
      confidence_label: 'medium',
      summary: 'Market is bullish.',
      overview: {
        generated_at: '2026-07-21T10:00:00Z',
        market_sentiment: 'bullish',
        confidence_label: 'medium',
        indexes: [],
        top_movers: [],
        signal_summary: [],
        commentary: 'Market is bullish.',
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

    const result = await fetchDailyMarketReportByDate('2026-07-21')

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/market/daily-report/2026-07-21')
    expect(result?.report_date).toBe('2026-07-21')
  })

  it('returns null when a dated report is missing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }))

    await expect(fetchDailyMarketReportByDate('2026-07-19')).resolves.toBeNull()
  })

  it('throws when a dated report request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }))

    await expect(fetchDailyMarketReportByDate('2026-07-21')).rejects.toThrow('daily market report fetch failed')
  })
})
