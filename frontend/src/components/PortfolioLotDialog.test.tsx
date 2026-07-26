import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchCards } from '../api/api'
import type { CardSummary, CardsResponse } from '../types/api'
import type { PortfolioLot, PortfolioPosition } from '../types/portfolio'
import PortfolioDeleteDialog from './PortfolioDeleteDialog'
import PortfolioLotDialog from './PortfolioLotDialog'

vi.mock('../api/api', () => ({
  fetchCards: vi.fn(),
}))

const fetchCardsMock = vi.mocked(fetchCards)

const moonbreonCard: CardSummary = {
  asset_id: 'asset-moonbreon',
  name: 'Moonbreon',
  set_name: 'Evolving Skies',
  rarity: 'secret',
  card_type: null,
  tcg_price: 200,
  ebay_price: null,
  signal: 'WATCH',
  price_delta_pct: 2.5,
  liquidity_score: 70,
  volume_24h: 4,
  image_url: null,
}

const existingCard: CardSummary = {
  ...moonbreonCard,
  asset_id: 'asset-existing',
  name: 'Existing Card',
}

const newCard: CardSummary = {
  ...moonbreonCard,
  asset_id: 'asset-new',
  name: 'New Card',
}

const lot: PortfolioLot = {
  id: 'lot-1',
  asset_id: moonbreonCard.asset_id,
  quantity: 2,
  unit_cost_usd: '160.00',
  purchased_on: '2026-07-10',
  created_at: '2026-07-10T00:00:00Z',
  updated_at: '2026-07-10T00:00:00Z',
}

const position: PortfolioPosition = {
  asset_id: moonbreonCard.asset_id,
  name: moonbreonCard.name,
  set_name: moonbreonCard.set_name,
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

function cardsResponse(cards: CardSummary[]): CardsResponse {
  return {
    cards,
    total: cards.length,
    limit: 8,
    offset: 0,
  }
}

function createProps(overrides = {}) {
  return {
    mode: 'create' as const,
    open: true,
    positionAssetIds: [] as string[],
    positionLimit: 10,
    busy: false,
    error: null,
    onClose: vi.fn(),
    onSubmit: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
}

async function runDebounce() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(300)
  })
}

async function selectMoonbreon() {
  fetchCardsMock.mockResolvedValueOnce(cardsResponse([moonbreonCard]))
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search cards' }), {
    target: { value: 'Moonbreon' },
  })
  await runDebounce()
  fireEvent.click(
    screen.getByRole('button', { name: 'Select Moonbreon' }),
  )
}

describe('PortfolioLotDialog create mode', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('resets create state every time it opens', () => {
    const props = createProps()
    const { rerender } = render(<PortfolioLotDialog {...props} />)
    const search = screen.getByRole('searchbox', { name: 'Search cards' })
    fireEvent.change(search, { target: { value: 'Moon' } })
    expect((search as HTMLInputElement).value).toBe('Moon')

    rerender(<PortfolioLotDialog {...props} open={false} />)
    rerender(<PortfolioLotDialog {...props} open />)

    expect(
      (screen.getByRole('searchbox', { name: 'Search cards' }) as HTMLInputElement)
        .value,
    ).toBe('')
    expect(screen.queryByLabelText('Quantity')).toBeNull()
  })

  it('waits 300ms before searching with the exact request contract', async () => {
    fetchCardsMock.mockResolvedValue(cardsResponse([]))
    render(<PortfolioLotDialog {...createProps()} />)

    fireEvent.change(screen.getByRole('searchbox', { name: 'Search cards' }), {
      target: { value: '  Moonbreon  ' },
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(299)
    })
    expect(fetchCardsMock).not.toHaveBeenCalled()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    expect(fetchCardsMock).toHaveBeenCalledWith({
      search: 'Moonbreon',
      sort: 'change',
      limit: 8,
    })
  })

  it('does not let an older search overwrite a newer result', async () => {
    let resolveOld: (value: CardsResponse) => void = () => undefined
    let resolveNew: (value: CardsResponse) => void = () => undefined
    const oldRequest = new Promise<CardsResponse>(resolve => {
      resolveOld = resolve
    })
    const newRequest = new Promise<CardsResponse>(resolve => {
      resolveNew = resolve
    })
    fetchCardsMock
      .mockReturnValueOnce(oldRequest)
      .mockReturnValueOnce(newRequest)
    render(<PortfolioLotDialog {...createProps()} />)
    const search = screen.getByRole('searchbox', { name: 'Search cards' })

    fireEvent.change(search, { target: { value: 'Old' } })
    await runDebounce()
    fireEvent.change(search, { target: { value: 'New' } })
    await runDebounce()

    await act(async () => {
      resolveNew(cardsResponse([newCard]))
      await newRequest
    })
    expect(screen.getByRole('button', { name: 'Select New Card' })).toBeTruthy()

    await act(async () => {
      resolveOld(cardsResponse([existingCard]))
      await oldRequest
    })
    expect(screen.getByRole('button', { name: 'Select New Card' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Select Existing Card' })).toBeNull()
  })

  it('reveals fields after card selection and submits the exact normalized input', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<PortfolioLotDialog {...createProps({ onSubmit })} />)
    await selectMoonbreon()

    fireEvent.change(screen.getByLabelText('Quantity'), {
      target: { value: '2' },
    })
    fireEvent.change(screen.getByLabelText('Unit cost (USD)'), {
      target: { value: '125' },
    })
    fireEvent.change(screen.getByLabelText('Purchase date'), {
      target: { value: '2026-07-01' },
    })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Add lot' }))
    })

    expect(onSubmit).toHaveBeenCalledWith({
      asset_id: moonbreonCard.asset_id,
      quantity: 2,
      unit_cost_usd: '125.00',
      purchased_on: '2026-07-01',
    })
  })

  it.each([
    {
      label: 'Quantity',
      value: '0',
      message: 'Enter a whole number of 1 or more.',
    },
    {
      label: 'Unit cost (USD)',
      value: '-1',
      message: 'Enter a non-negative amount with up to two decimals.',
    },
    {
      label: 'Unit cost (USD)',
      value: '1.234',
      message: 'Enter a non-negative amount with up to two decimals.',
    },
    {
      label: 'Purchase date',
      value: '',
      message: 'Choose a purchase date.',
    },
  ])('shows an inline error for invalid $label', async ({ label, value, message }) => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<PortfolioLotDialog {...createProps({ onSubmit })} />)
    await selectMoonbreon()
    fireEvent.change(screen.getByLabelText('Quantity'), {
      target: { value: '1' },
    })
    fireEvent.change(screen.getByLabelText('Unit cost (USD)'), {
      target: { value: '10.00' },
    })
    fireEvent.change(screen.getByLabelText('Purchase date'), {
      target: { value: '2026-07-01' },
    })

    fireEvent.change(screen.getByLabelText(label), {
      target: { value },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add lot' }))

    expect(screen.getByText(message)).toBeTruthy()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('allows existing positions at the Free limit and blocks only new assets', async () => {
    fetchCardsMock.mockResolvedValueOnce(cardsResponse([existingCard, newCard]))
    render(
      <PortfolioLotDialog
        {...createProps({
          positionAssetIds: [existingCard.asset_id],
          positionLimit: 1,
        })}
      />,
    )

    fireEvent.change(screen.getByRole('searchbox', { name: 'Search cards' }), {
      target: { value: 'Card' },
    })
    await runDebounce()

    const existing = screen.getByRole('button', { name: 'Select Existing Card' })
    const blocked = screen.getByRole('button', { name: 'Select New Card' })
    expect((existing as HTMLButtonElement).disabled).toBe(false)
    expect((blocked as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText('New position unavailable on Free')).toBeTruthy()
    expect(
      screen.getByRole('link', { name: 'View upgrade options' }).getAttribute('href'),
    ).toBe('/pricing')

    fireEvent.click(existing)
    expect(screen.getByLabelText('Quantity')).toBeTruthy()
  })
})

describe('PortfolioLotDialog edit mode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('keeps identity read-only, pre-fills values, and sends only editable fields', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(
      <PortfolioLotDialog
        mode="edit"
        open
        position={position}
        lot={lot}
        busy={false}
        error={null}
        onClose={vi.fn()}
        onSubmit={onSubmit}
      />,
    )

    expect(screen.getByText('Moonbreon')).toBeTruthy()
    expect(screen.queryByRole('searchbox')).toBeNull()
    expect((screen.getByLabelText('Quantity') as HTMLInputElement).value).toBe('2')
    expect((screen.getByLabelText('Unit cost (USD)') as HTMLInputElement).value)
      .toBe('160.00')
    expect((screen.getByLabelText('Purchase date') as HTMLInputElement).value)
      .toBe('2026-07-10')

    fireEvent.change(screen.getByLabelText('Quantity'), {
      target: { value: '3' },
    })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Save changes' }))
    })

    expect(onSubmit).toHaveBeenCalledWith({
      quantity: 3,
      unit_cost_usd: '160.00',
      purchased_on: '2026-07-10',
    })
  })

  it.each(['escape', 'button'])('restores opener focus after closing by %s', method => {
    function Harness() {
      const [open, setOpen] = useState(false)
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>Open editor</button>
          <PortfolioLotDialog
            mode="edit"
            open={open}
            position={position}
            lot={lot}
            busy={false}
            error={null}
            onClose={() => setOpen(false)}
            onSubmit={vi.fn().mockResolvedValue(undefined)}
          />
        </>
      )
    }

    render(<Harness />)
    const opener = screen.getByRole('button', { name: 'Open editor' })
    opener.focus()
    fireEvent.click(opener)
    const dialog = screen.getByRole('dialog', { name: 'Edit portfolio lot' })
    if (method === 'escape') {
      fireEvent.keyDown(dialog, { key: 'Escape' })
    } else {
      fireEvent.click(
        within(dialog).getByRole('button', {
          name: 'Close portfolio lot dialog',
        }),
      )
    }

    expect(screen.queryByRole('dialog')).toBeNull()
    expect(document.activeElement).toBe(opener)
  })
})

describe('PortfolioDeleteDialog', () => {
  it('names the lot and Cancel closes without deleting', () => {
    const onClose = vi.fn()
    const onConfirm = vi.fn().mockResolvedValue(undefined)
    render(
      <PortfolioDeleteDialog
        open
        position={position}
        lot={lot}
        busy={false}
        onClose={onClose}
        onConfirm={onConfirm}
      />,
    )

    expect(screen.getByText('Moonbreon')).toBeTruthy()
    expect(screen.getByText('Jul 10, 2026')).toBeTruthy()
    expect(screen.getByText('Quantity: 2')).toBeTruthy()
    expect(screen.getByText('Unit cost: $160.00')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onClose).toHaveBeenCalledOnce()
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('confirms the exact lot once', async () => {
    const onConfirm = vi.fn().mockResolvedValue(undefined)
    render(
      <PortfolioDeleteDialog
        open
        position={position}
        lot={lot}
        busy={false}
        onClose={vi.fn()}
        onConfirm={onConfirm}
      />,
    )

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Delete lot' }))
    })

    expect(onConfirm).toHaveBeenCalledOnce()
    expect(onConfirm).toHaveBeenCalledWith(lot.id)
  })

  it('prevents repeat submission and outside close while busy', () => {
    const onClose = vi.fn()
    const onConfirm = vi.fn().mockResolvedValue(undefined)
    render(
      <PortfolioDeleteDialog
        open
        position={position}
        lot={lot}
        busy
        onClose={onClose}
        onConfirm={onConfirm}
      />,
    )

    const deleteButton = screen.getByRole('button', { name: 'Deleting lot' })
    const cancelButton = screen.getByRole('button', { name: 'Cancel' })
    expect((deleteButton as HTMLButtonElement).disabled).toBe(true)
    expect((cancelButton as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByTestId('portfolio-delete-backdrop'))
    fireEvent.click(deleteButton)

    expect(onClose).not.toHaveBeenCalled()
    expect(onConfirm).not.toHaveBeenCalled()
  })
})
