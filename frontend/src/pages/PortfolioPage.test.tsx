import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  PortfolioApiError,
  createPortfolioLot,
  deletePortfolioLot,
  fetchPortfolio,
  updatePortfolioLot,
} from '../api/portfolio'
import { useUser } from '../hooks/useUser'
import type {
  Portfolio,
  PortfolioLot,
  PortfolioLotInput,
  PortfolioLotPatch,
  PortfolioPosition,
  PortfolioSummary,
} from '../types/portfolio'
import PortfolioPage from './PortfolioPage'

vi.mock('../hooks/useUser', () => ({
  useUser: vi.fn(),
}))

vi.mock('../api/portfolio', async importOriginal => {
  const actual = await importOriginal<typeof import('../api/portfolio')>()
  return {
    ...actual,
    fetchPortfolio: vi.fn(),
    createPortfolioLot: vi.fn(),
    updatePortfolioLot: vi.fn(),
    deletePortfolioLot: vi.fn(),
  }
})

vi.mock('../components/NavBar', () => ({
  default: () => <nav>Navigation</nav>,
}))

vi.mock('../components/PortfolioSummary', () => ({
  default: ({ summary }: { summary: PortfolioSummary }) => (
    <section aria-label="Portfolio summary">
      Total {summary.total_cost_basis}; Value {summary.total_market_value}
    </section>
  ),
}))

vi.mock('../components/PortfolioAllocation', () => ({
  default: ({
    allocations,
    unpricedPositionCount,
  }: {
    allocations: Portfolio['allocations']
    unpricedPositionCount: number
  }) => (
    <section aria-label="Portfolio allocation">
      {allocations.map(item => item.game).join(', ')}
      {unpricedPositionCount > 0 && (
        <span>
          {unpricedPositionCount}{' '}
          {unpricedPositionCount === 1 ? 'position is' : 'positions are'} missing
          a raw market price
        </span>
      )}
    </section>
  ),
}))

vi.mock('../components/PortfolioPositionTable', () => ({
  default: ({
    positions,
    onEditLot,
    onDeleteLot,
  }: {
    positions: PortfolioPosition[]
    onEditLot: (position: PortfolioPosition, lot: PortfolioLot) => void
    onDeleteLot: (position: PortfolioPosition, lot: PortfolioLot) => void
  }) => (
    <section aria-label="Portfolio positions">
      {positions.map(position => (
        <div key={position.asset_id}>
          <span>{position.name}</span>
          {position.lots[0] && (
            <>
              <button
                type="button"
                onClick={() => onEditLot(position, position.lots[0])}
              >
                Edit {position.name}
              </button>
              <button
                type="button"
                onClick={() => onDeleteLot(position, position.lots[0])}
              >
                Delete {position.name}
              </button>
            </>
          )}
        </div>
      ))}
    </section>
  ),
}))

interface MockLotDialogProps {
  mode: 'create' | 'edit'
  open: boolean
  busy: boolean
  error: string | null
  upgradeUrl?: string | null
  onSubmit: (
    input: PortfolioLotInput | PortfolioLotPatch,
  ) => Promise<void>
}

vi.mock('../components/PortfolioLotDialog', () => ({
  default: (props: MockLotDialogProps) => {
    if (!props.open) return null
    const input = props.mode === 'create'
      ? {
          asset_id: 'asset-created',
          quantity: 1,
          unit_cost_usd: '25.00',
          purchased_on: '2026-07-20',
        }
      : {
          quantity: 3,
          unit_cost_usd: '150.00',
          purchased_on: '2026-07-10',
        }
    return (
      <div role="dialog" aria-label={`${props.mode} lot dialog`}>
        {props.error && <span>{props.error}</span>}
        {props.upgradeUrl && (
          <a href={props.upgradeUrl}>View upgrade options</a>
        )}
        <button
          type="button"
          disabled={props.busy}
          onClick={() => {
            void props.onSubmit(input)
          }}
        >
          {props.busy ? 'Mutation pending' : `Submit ${props.mode}`}
        </button>
      </div>
    )
  },
}))

interface MockDeleteDialogProps {
  open: boolean
  busy: boolean
  lot: PortfolioLot | null
  onConfirm: (lotId: string) => Promise<void>
}

vi.mock('../components/PortfolioDeleteDialog', () => ({
  default: (props: MockDeleteDialogProps) => {
    if (!props.open || !props.lot) return null
    return (
      <div role="dialog" aria-label="delete lot dialog">
        <button
          type="button"
          disabled={props.busy}
          onClick={() => {
            if (props.lot) void props.onConfirm(props.lot.id)
          }}
        >
          {props.busy ? 'Delete pending' : 'Confirm delete'}
        </button>
      </div>
    )
  },
}))

const useUserMock = vi.mocked(useUser)
const fetchPortfolioMock = vi.mocked(fetchPortfolio)
const createPortfolioLotMock = vi.mocked(createPortfolioLot)
const updatePortfolioLotMock = vi.mocked(updatePortfolioLot)
const deletePortfolioLotMock = vi.mocked(deletePortfolioLot)

const lot: PortfolioLot = {
  id: 'lot-1',
  asset_id: 'asset-moonbreon',
  quantity: 2,
  unit_cost_usd: '160.00',
  purchased_on: '2026-07-10',
  created_at: '2026-07-10T00:00:00Z',
  updated_at: '2026-07-10T00:00:00Z',
}

const position: PortfolioPosition = {
  asset_id: 'asset-moonbreon',
  name: 'Moonbreon',
  set_name: 'Evolving Skies',
  card_number: '215/203',
  game: 'pokemon',
  quantity: 2,
  average_unit_cost_usd: '160.00',
  cost_basis_usd: '320.00',
  latest_raw_price_usd: '200.00',
  latest_price_at: '2026-07-26T00:00:00Z',
  market_value_usd: '400.00',
  unrealized_pnl_usd: '80.00',
  unrealized_pnl_percent: '25.00',
  valuation_status: 'priced',
  lots: [lot],
}

const emptyPortfolio: Portfolio = {
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

const portfolio: Portfolio = {
  summary: {
    total_cost_basis: '370.00',
    priced_cost_basis: '320.00',
    total_market_value: '400.00',
    unrealized_pnl: '80.00',
    unrealized_pnl_percent: '25.00',
    position_count: 2,
    priced_position_count: 1,
    unpriced_position_count: 1,
    valuation_coverage_percent: '50.00',
    position_limit: 10,
  },
  allocations: [
    {
      game: 'pokemon',
      market_value_usd: '400.00',
      percentage: '100.00',
      priced_position_count: 1,
    },
  ],
  positions: [
    position,
    {
      ...position,
      asset_id: 'asset-unpriced',
      name: 'Unpriced Promo',
      quantity: 1,
      cost_basis_usd: '50.00',
      average_unit_cost_usd: '50.00',
      latest_raw_price_usd: null,
      latest_price_at: null,
      market_value_usd: null,
      unrealized_pnl_usd: null,
      unrealized_pnl_percent: null,
      valuation_status: 'unpriced',
      lots: [],
    },
  ],
}

function deferred<T>() {
  let resolve: (value: T) => void = () => undefined
  let reject: (reason?: unknown) => void = () => undefined
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

describe('PortfolioPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useUserMock.mockReturnValue({
      email: 'collector@example.com',
      tier: 'free',
      loading: false,
      setDevTier: vi.fn(),
    })
    createPortfolioLotMock.mockResolvedValue(lot)
    updatePortfolioLotMock.mockResolvedValue(lot)
    deletePortfolioLotMock.mockResolvedValue(undefined)
  })

  it('shows stable skeletons without requesting data while user state loads', () => {
    useUserMock.mockReturnValue({
      email: null,
      tier: 'free',
      loading: true,
      setDevTier: vi.fn(),
    })

    render(<PortfolioPage />)

    expect(screen.getAllByTestId('portfolio-skeleton')).toHaveLength(4)
    expect(fetchPortfolioMock).not.toHaveBeenCalled()
  })

  it('shows a sign-in state without requesting a portfolio', () => {
    useUserMock.mockReturnValue({
      email: null,
      tier: 'free',
      loading: false,
      setDevTier: vi.fn(),
    })

    render(<PortfolioPage />)

    expect(screen.getByText('Sign in to view your portfolio')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Sign in' }).getAttribute('href'))
      .toBe('/login')
    expect(fetchPortfolioMock).not.toHaveBeenCalled()
  })

  it('shows the empty call to action after an authenticated empty response', async () => {
    fetchPortfolioMock.mockResolvedValueOnce(emptyPortfolio)

    render(<PortfolioPage />)

    expect(await screen.findByText('Add your first position')).toBeTruthy()
    expect(screen.getByText('0 of 10 positions used')).toBeTruthy()
  })

  it('renders summary, allocation, positions, and partial coverage', async () => {
    fetchPortfolioMock.mockResolvedValueOnce(portfolio)

    render(<PortfolioPage />)

    expect(await screen.findByText('Moonbreon')).toBeTruthy()
    expect(screen.getByLabelText('Portfolio summary').textContent)
      .toContain('Total 370.00')
    expect(screen.getByLabelText('Portfolio allocation').textContent)
      .toContain('pokemon')
    expect(
      screen.getByText('1 position is missing a raw market price'),
    ).toBeTruthy()
    expect(screen.getByText('2 of 10 positions used')).toBeTruthy()
  })

  it('retries a failed initial request successfully', async () => {
    fetchPortfolioMock
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(portfolio)

    render(<PortfolioPage />)

    expect(await screen.findByText('Portfolio data is unavailable.')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))

    expect(await screen.findByText('Moonbreon')).toBeTruthy()
    expect(fetchPortfolioMock).toHaveBeenCalledTimes(2)
  })

  it('keeps existing data visible when a post-mutation refresh fails', async () => {
    fetchPortfolioMock
      .mockResolvedValueOnce(portfolio)
      .mockRejectedValueOnce(new Error('refresh failed'))

    render(<PortfolioPage />)
    await screen.findByText('Moonbreon')
    fireEvent.click(screen.getByRole('button', { name: 'Add lot' }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit create' }))

    expect(await screen.findByText('Portfolio data is unavailable.')).toBeTruthy()
    expect(screen.getByText('Moonbreon')).toBeTruthy()
    expect(screen.getByRole('dialog', { name: 'create lot dialog' })).toBeTruthy()
  })

  it('runs create, edit, and delete mutations followed by refreshes', async () => {
    fetchPortfolioMock.mockResolvedValue(portfolio)

    render(<PortfolioPage />)
    await screen.findByText('Moonbreon')

    fireEvent.click(screen.getByRole('button', { name: 'Add lot' }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit create' }))
    await waitFor(() => expect(createPortfolioLotMock).toHaveBeenCalledOnce())
    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'create lot dialog' }))
        .toBeNull()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Edit Moonbreon' }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit edit' }))
    await waitFor(() => {
      expect(updatePortfolioLotMock).toHaveBeenCalledWith(lot.id, {
        quantity: 3,
        unit_cost_usd: '150.00',
        purchased_on: '2026-07-10',
      })
    })

    fireEvent.click(screen.getByRole('button', { name: 'Delete Moonbreon' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirm delete' }))
    await waitFor(() => {
      expect(deletePortfolioLotMock).toHaveBeenCalledWith(lot.id)
    })
    expect(fetchPortfolioMock).toHaveBeenCalledTimes(4)
  })

  it('disables mutation submission while the request is pending', async () => {
    const mutation = deferred<PortfolioLot>()
    fetchPortfolioMock.mockResolvedValue(portfolio)
    createPortfolioLotMock.mockReturnValueOnce(mutation.promise)

    render(<PortfolioPage />)
    await screen.findByText('Moonbreon')
    fireEvent.click(screen.getByRole('button', { name: 'Add lot' }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit create' }))

    const pending = await screen.findByRole('button', {
      name: 'Mutation pending',
    })
    expect((pending as HTMLButtonElement).disabled).toBe(true)

    await act(async () => {
      mutation.resolve(lot)
      await mutation.promise
    })
  })

  it('preserves structured limit details and the upgrade link', async () => {
    const detail = {
      code: 'portfolio_position_limit_reached',
      message: 'Free accounts can hold up to 10 portfolio positions.',
      position_limit: 10,
      position_count: 10,
      upgrade_url: '/pricing',
    }
    fetchPortfolioMock.mockResolvedValueOnce(portfolio)
    createPortfolioLotMock.mockRejectedValueOnce(
      new PortfolioApiError(403, detail),
    )

    render(<PortfolioPage />)
    await screen.findByText('Moonbreon')
    fireEvent.click(screen.getByRole('button', { name: 'Add lot' }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit create' }))

    expect(await screen.findByText(detail.message)).toBeTruthy()
    expect(
      screen.getByRole('link', { name: 'View upgrade options' })
        .getAttribute('href'),
    ).toBe('/pricing')
  })

  it('ignores a late initial response after a newer mutation refresh', async () => {
    const initial = deferred<Portfolio>()
    const refreshed = {
      ...portfolio,
      positions: [{ ...position, name: 'New Refresh Card' }],
    }
    fetchPortfolioMock
      .mockReturnValueOnce(initial.promise)
      .mockResolvedValueOnce(refreshed)

    render(<PortfolioPage />)
    fireEvent.click(screen.getByRole('button', { name: 'Add lot' }))
    fireEvent.click(screen.getByRole('button', { name: 'Submit create' }))

    expect(await screen.findByText('New Refresh Card')).toBeTruthy()
    await act(async () => {
      initial.resolve(portfolio)
      await initial.promise
    })

    expect(screen.getByText('New Refresh Card')).toBeTruthy()
    expect(screen.queryByText('Moonbreon')).toBeNull()
  })
})
