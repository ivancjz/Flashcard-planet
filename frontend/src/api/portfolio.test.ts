import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  PortfolioApiError,
  createPortfolioLot,
  deletePortfolioLot,
  fetchPortfolio,
  updatePortfolioLot,
} from './portfolio'

const portfolioFixture = {
  summary: {
    total_cost_basis: '0.00',
    priced_cost_basis: '0.00',
    total_market_value: '0.00',
    unrealized_pnl: '0.00',
    unrealized_pnl_percent: null,
    position_count: 0,
    priced_position_count: 0,
    unpriced_position_count: 0,
    valuation_coverage_percent: '0.00',
    position_limit: 10,
  },
  allocations: [],
  positions: [],
}

describe('portfolio API client', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches the authenticated portfolio from the same origin', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue(portfolioFixture),
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchPortfolio()).resolves.toBe(portfolioFixture)
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/portfolio', {
      credentials: 'same-origin',
    })
  })

  it('creates a portfolio lot with the exact JSON contract', async () => {
    const lot = { id: 'lot-1' }
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: vi.fn().mockResolvedValue(lot),
    })
    vi.stubGlobal('fetch', fetchMock)

    await createPortfolioLot({
      asset_id: 'asset-1',
      quantity: 2,
      unit_cost_usd: '125.00',
      purchased_on: '2026-07-01',
    })

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/portfolio/lots', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        asset_id: 'asset-1',
        quantity: 2,
        unit_cost_usd: '125.00',
        purchased_on: '2026-07-01',
      }),
    })
  })

  it('updates an encoded lot path with only supplied fields', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ id: 'lot/1' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await updatePortfolioLot('lot/1', {
      quantity: 3,
      unit_cost_usd: '120.00',
    })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/portfolio/lots/lot%2F1',
      {
        method: 'PATCH',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          quantity: 3,
          unit_cost_usd: '120.00',
        }),
      },
    )
  })

  it('deletes an encoded lot path and accepts an empty 204 response', async () => {
    const json = vi.fn()
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      json,
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(deletePortfolioLot('lot/1')).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/portfolio/lots/lot%2F1',
      {
        method: 'DELETE',
        credentials: 'same-origin',
      },
    )
    expect(json).not.toHaveBeenCalled()
  })

  it('throws a typed error for unauthenticated requests', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: vi.fn().mockResolvedValue({ detail: 'Not authenticated.' }),
    }))

    const request = fetchPortfolio()

    await expect(request).rejects.toBeInstanceOf(PortfolioApiError)
    await expect(request).rejects.toMatchObject({
      status: 401,
      detail: 'Not authenticated.',
      message: 'Not authenticated.',
    })
  })

  it('preserves the structured position-limit detail', async () => {
    const detail = {
      code: 'portfolio_position_limit_reached',
      message: 'Free accounts can hold up to 10 portfolio positions.',
      position_limit: 10,
      position_count: 10,
      upgrade_url: '/pricing',
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: vi.fn().mockResolvedValue({ detail }),
    }))

    await expect(createPortfolioLot({
      asset_id: 'asset-11',
      quantity: 1,
      unit_cost_usd: '10.00',
      purchased_on: '2026-07-01',
    })).rejects.toMatchObject({
      status: 403,
      detail,
      message: detail.message,
    })
  })

  it('uses a stable message when an error body is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: vi.fn().mockRejectedValue(new SyntaxError('invalid JSON')),
    }))

    await expect(fetchPortfolio()).rejects.toMatchObject({
      status: 500,
      detail: null,
      message: 'Portfolio request failed.',
    })
  })
})
