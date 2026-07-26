import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type {
  PortfolioAllocation as PortfolioAllocationType,
  PortfolioPosition,
  PortfolioSummary as PortfolioSummaryType,
} from '../types/portfolio'
import PortfolioAllocation from './PortfolioAllocation'
import PortfolioPositionTable from './PortfolioPositionTable'
import PortfolioSummary from './PortfolioSummary'

const summary: PortfolioSummaryType = {
  total_cost_basis: '410.00',
  priced_cost_basis: '360.00',
  total_market_value: '600.00',
  unrealized_pnl: '240.00',
  unrealized_pnl_percent: '66.67',
  position_count: 2,
  priced_position_count: 1,
  unpriced_position_count: 1,
  valuation_coverage_percent: '50.00',
  position_limit: 10,
}

const allocations: PortfolioAllocationType[] = [
  {
    game: 'pokemon',
    market_value_usd: '450.00',
    percentage: '75.00',
    priced_position_count: 1,
  },
  {
    game: 'one_piece',
    market_value_usd: '150.00',
    percentage: '25.00',
    priced_position_count: 1,
  },
]

const moonbreon: PortfolioPosition = {
  asset_id: 'asset-moonbreon',
  name: 'Moonbreon',
  set_name: 'Evolving Skies',
  card_number: '215/203',
  game: 'pokemon',
  quantity: 3,
  average_unit_cost_usd: '120.00',
  cost_basis_usd: '360.00',
  latest_raw_price_usd: '200.00',
  latest_price_at: '2026-07-26T00:00:00Z',
  market_value_usd: '600.00',
  unrealized_pnl_usd: '240.00',
  unrealized_pnl_percent: '66.67',
  valuation_status: 'priced',
  lots: [
    {
      id: 'lot-new',
      asset_id: 'asset-moonbreon',
      quantity: 1,
      unit_cost_usd: '160.00',
      purchased_on: '2026-07-10',
      created_at: '2026-07-10T00:00:00Z',
      updated_at: '2026-07-10T00:00:00Z',
    },
    {
      id: 'lot-old',
      asset_id: 'asset-moonbreon',
      quantity: 2,
      unit_cost_usd: '100.00',
      purchased_on: '2026-07-01',
      created_at: '2026-07-01T00:00:00Z',
      updated_at: '2026-07-01T00:00:00Z',
    },
  ],
}

const unpricedPosition: PortfolioPosition = {
  asset_id: 'asset-unpriced',
  name: 'Unpriced Promo',
  set_name: null,
  card_number: null,
  game: 'pokemon',
  quantity: 1,
  average_unit_cost_usd: '50.00',
  cost_basis_usd: '50.00',
  latest_raw_price_usd: null,
  latest_price_at: null,
  market_value_usd: null,
  unrealized_pnl_usd: null,
  unrealized_pnl_percent: null,
  valuation_status: 'unpriced',
  lots: [],
}

function renderReadView(
  onEditLot = vi.fn(),
  onDeleteLot = vi.fn(),
) {
  return render(
    <>
      <PortfolioSummary summary={summary} />
      <PortfolioAllocation
        allocations={allocations}
        unpricedPositionCount={1}
      />
      <PortfolioPositionTable
        positions={[moonbreon, unpricedPosition]}
        onEditLot={onEditLot}
        onDeleteLot={onDeleteLot}
      />
    </>,
  )
}

describe('Portfolio read view', () => {
  it('renders stable summary values and a visible positive P&L label', () => {
    render(<PortfolioSummary summary={summary} />)

    expect(screen.getByText('Total cost')).toBeTruthy()
    expect(screen.getByText('$410.00')).toBeTruthy()
    expect(screen.getByText('Current value')).toBeTruthy()
    expect(screen.getByText('$600.00')).toBeTruthy()
    expect(screen.getByText('Unrealized P&L')).toBeTruthy()
    expect(screen.getByText('+$240.00')).toBeTruthy()
    expect(screen.getByText('Gain')).toBeTruthy()
    expect(screen.getByText('Valuation coverage')).toBeTruthy()
    expect(screen.getByText('50.00%')).toBeTruthy()
  })

  it('renders a visible negative P&L amount and loss label', () => {
    render(
      <PortfolioSummary
        summary={{
          ...summary,
          unrealized_pnl: '-25.00',
          unrealized_pnl_percent: '-6.94',
        }}
      />,
    )

    expect(screen.getByText('-$25.00')).toBeTruthy()
    expect(screen.getByText('Loss')).toBeTruthy()
  })

  it('labels allocation segments and explains missing raw prices', () => {
    render(
      <PortfolioAllocation
        allocations={allocations}
        unpricedPositionCount={1}
      />,
    )

    expect(
      screen.getByLabelText('Pokemon: 75.00% of priced market value'),
    ).toBeTruthy()
    expect(
      screen.getByLabelText('One Piece: 25.00% of priced market value'),
    ).toBeTruthy()
    expect(
      screen.getByText('1 position is missing a raw market price'),
    ).toBeTruthy()
  })

  it('shows Unpriced instead of a false zero market value', () => {
    renderReadView()

    const row = screen.getByText('Unpriced Promo').closest('tr')
    expect(row).not.toBeNull()
    expect(within(row as HTMLTableRowElement).getByText('Unpriced')).toBeTruthy()
    expect(within(row as HTMLTableRowElement).queryByText('$0.00')).toBeNull()
  })

  it('expands lots in purchase-date order with accessible actions', async () => {
    const user = userEvent.setup()
    renderReadView()

    await user.click(
      screen.getByRole('button', { name: 'Expand lots for Moonbreon' }),
    )

    const lotTable = screen.getByRole('table', {
      name: 'Purchase lots for Moonbreon',
    })
    const dates = within(lotTable)
      .getAllByRole('row')
      .slice(1)
      .map(row => within(row).getAllByRole('cell')[0].textContent)

    expect(dates).toEqual(['Jul 10, 2026', 'Jul 1, 2026'])
    expect(
      within(lotTable).getByRole('button', {
        name: 'Edit lot purchased Jul 10, 2026',
      }),
    ).toBeTruthy()
    expect(
      within(lotTable).getByRole('button', {
        name: 'Delete lot purchased Jul 10, 2026',
      }),
    ).toBeTruthy()
  })

  it('passes the exact selected position and lot to action callbacks', async () => {
    const user = userEvent.setup()
    const onEditLot = vi.fn()
    const onDeleteLot = vi.fn()
    renderReadView(onEditLot, onDeleteLot)

    await user.click(
      screen.getByRole('button', { name: 'Expand lots for Moonbreon' }),
    )
    await user.click(
      screen.getByRole('button', {
        name: 'Edit lot purchased Jul 10, 2026',
      }),
    )
    await user.click(
      screen.getByRole('button', {
        name: 'Delete lot purchased Jul 10, 2026',
      }),
    )

    expect(onEditLot).toHaveBeenCalledWith(moonbreon, moonbreon.lots[0])
    expect(onDeleteLot).toHaveBeenCalledWith(moonbreon, moonbreon.lots[0])
  })

  it('renders the empty-allocation state when no raw prices exist', () => {
    render(
      <PortfolioAllocation
        allocations={[]}
        unpricedPositionCount={2}
      />,
    )

    expect(
      screen.getByText(
        'No raw market prices are available for allocation yet.',
      ),
    ).toBeTruthy()
  })
})
