import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchMarketOverview } from './api'

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
