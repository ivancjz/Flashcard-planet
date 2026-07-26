import {
  type FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react'
import { X } from 'lucide-react'
import { fetchCards } from '../api/api'
import { useFocusTrap } from '../hooks/useFocusTrap'
import { useScrollLock } from '../hooks/useScrollLock'
import type { CardSummary } from '../types/api'
import type {
  PortfolioLot,
  PortfolioLotInput,
  PortfolioLotPatch,
  PortfolioPosition,
} from '../types/portfolio'

type PortfolioLotDialogProps =
  | {
      mode: 'create'
      open: boolean
      positionAssetIds: string[]
      positionLimit: number | null
      busy: boolean
      error: string | null
      upgradeUrl?: string | null
      onClose: () => void
      onSubmit: (input: PortfolioLotInput) => Promise<void>
    }
  | {
      mode: 'edit'
      open: boolean
      position: PortfolioPosition
      lot: PortfolioLot
      busy: boolean
      error: string | null
      upgradeUrl?: string | null
      onClose: () => void
      onSubmit: (input: PortfolioLotPatch) => Promise<void>
    }

type SearchState = 'idle' | 'loading' | 'ready' | 'error'

interface FieldErrors {
  quantity?: string
  unitCost?: string
  purchasedOn?: string
}

const quantityPattern = /^[1-9]\d*$/
const costPattern = /^(0|[1-9]\d*)(\.\d{1,2})?$/
const datePattern = /^\d{4}-\d{2}-\d{2}$/

function cardMeta(card: CardSummary): string {
  return [card.set_name, card.rarity].filter(Boolean).join(' / ')
}

export default function PortfolioLotDialog(props: PortfolioLotDialogProps) {
  if (!props.open) return null
  const dialogKey = props.mode === 'edit' ? props.lot.id : 'create'
  return <PortfolioLotDialogContent key={dialogKey} {...props} />
}

function PortfolioLotDialogContent(props: PortfolioLotDialogProps) {
  const {
    mode,
    busy,
    error,
    upgradeUrl,
    onClose,
  } = props
  const editLot = mode === 'edit' ? props.lot : null
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<CardSummary[]>([])
  const [searchState, setSearchState] = useState<SearchState>('idle')
  const [selectedCard, setSelectedCard] = useState<CardSummary | null>(null)
  const [quantity, setQuantity] = useState(
    () => editLot ? String(editLot.quantity) : '1',
  )
  const [unitCost, setUnitCost] = useState(
    () => editLot?.unit_cost_usd ?? '',
  )
  const [purchasedOn, setPurchasedOn] = useState(
    () => editLot?.purchased_on ?? '',
  )
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const requestSequence = useRef(0)
  const searchInputRef = useRef<HTMLInputElement>(null)
  const busyRef = useRef(busy)
  const onCloseRef = useRef(onClose)

  useEffect(() => {
    busyRef.current = busy
    onCloseRef.current = onClose
  }, [busy, onClose])

  const requestClose = useCallback(() => {
    if (!busyRef.current) onCloseRef.current()
  }, [])
  const trapRef = useFocusTrap<HTMLDivElement>(true, requestClose)
  useScrollLock(true)

  useEffect(() => {
    if (mode === 'create') searchInputRef.current?.focus()
  }, [mode])

  useEffect(() => () => {
    requestSequence.current += 1
  }, [])

  useEffect(() => {
    if (mode !== 'create' || !query.trim()) return
    const normalizedQuery = query.trim()
    const sequence = requestSequence.current
    const timer = window.setTimeout(() => {
      setSearchState('loading')
      fetchCards({
        search: normalizedQuery,
        sort: 'change',
        limit: 8,
      }).then(result => {
        if (sequence !== requestSequence.current) return
        setResults(result.cards)
        setSearchState('ready')
      }).catch(() => {
        if (sequence !== requestSequence.current) return
        setResults([])
        setSearchState('error')
      })
    }, 300)
    return () => window.clearTimeout(timer)
  }, [mode, query])

  function changeQuery(value: string) {
    requestSequence.current += 1
    setQuery(value)
    setResults([])
    setSearchState('idle')
  }
  const atLimit = mode === 'create'
    && props.positionLimit !== null
    && props.positionAssetIds.length >= props.positionLimit
  const hasBlockedResult = mode === 'create'
    && results.some(card => (
      atLimit && !props.positionAssetIds.includes(card.asset_id)
    ))
  const activePosition = mode === 'edit' ? props.position : selectedCard
  const title = mode === 'create' ? 'Add portfolio lot' : 'Edit portfolio lot'

  function chooseCard(card: CardSummary) {
    if (mode !== 'create') return
    const isExistingPosition = props.positionAssetIds.includes(card.asset_id)
    if (atLimit && !isExistingPosition) return
    setSelectedCard(card)
    setFieldErrors({})
  }

  function validate(): FieldErrors {
    const next: FieldErrors = {}
    if (!quantityPattern.test(quantity)) {
      next.quantity = 'Enter a whole number of 1 or more.'
    }
    if (!costPattern.test(unitCost)) {
      next.unitCost = 'Enter a non-negative amount with up to two decimals.'
    }
    if (!datePattern.test(purchasedOn)) {
      next.purchasedOn = 'Choose a purchase date.'
    }
    return next
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const nextErrors = validate()
    setFieldErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0 || busy) return

    const editable = {
      quantity: Number(quantity),
      unit_cost_usd: Number(unitCost).toFixed(2),
      purchased_on: purchasedOn,
    }
    if (props.mode === 'create') {
      if (!selectedCard) return
      await props.onSubmit({
        asset_id: selectedCard.asset_id,
        ...editable,
      })
    } else {
      await props.onSubmit(editable)
    }
  }

  return (
    <>
      <div
        className="modal-backdrop portfolio-dialog-backdrop"
        onMouseDown={requestClose}
        aria-hidden="true"
      />
      <div
        ref={trapRef}
        className="modal portfolio-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="portfolio-lot-dialog-title"
        aria-busy={busy || undefined}
      >
        <header className="portfolio-dialog-header">
          <div>
            <span className="portfolio-dialog-eyebrow">Portfolio</span>
            <h2 id="portfolio-lot-dialog-title">{title}</h2>
          </div>
          <button
            type="button"
            className="icon-button portfolio-dialog-close"
            aria-label="Close portfolio lot dialog"
            title="Close portfolio lot dialog"
            disabled={busy}
            onClick={requestClose}
          >
            <X size={18} aria-hidden="true" />
          </button>
        </header>

        <div className="portfolio-dialog-body">
          {mode === 'create' && !selectedCard && (
            <div className="portfolio-card-picker">
              <label htmlFor="portfolio-card-search">Search cards</label>
              <input
                ref={searchInputRef}
                id="portfolio-card-search"
                type="search"
                value={query}
                placeholder="Search by card name"
                autoComplete="off"
                onChange={event => changeQuery(event.target.value)}
              />

              <div
                className="portfolio-search-results"
                aria-live="polite"
                aria-busy={searchState === 'loading' || undefined}
              >
                {!query.trim() && (
                  <p>Search for the card you purchased.</p>
                )}
                {query.trim() && searchState === 'loading' && (
                  <p>Searching cards...</p>
                )}
                {query.trim() && searchState === 'error' && (
                  <p>Card search is unavailable.</p>
                )}
                {query.trim()
                  && searchState === 'ready'
                  && results.length === 0 && (
                    <p>No cards match this search.</p>
                  )}
                {results.map(card => {
                  const isExistingPosition = props.positionAssetIds.includes(
                    card.asset_id,
                  )
                  const blocked = atLimit && !isExistingPosition
                  return (
                    <button
                      type="button"
                      className="portfolio-search-result option-row"
                      key={card.asset_id}
                      aria-label={`Select ${card.name}`}
                      disabled={blocked}
                      onClick={() => chooseCard(card)}
                    >
                      <span>
                        <strong>{card.name}</strong>
                        <span>{cardMeta(card)}</span>
                      </span>
                      {blocked ? (
                        <span>New position unavailable on Free</span>
                      ) : isExistingPosition ? (
                        <span>Existing position</span>
                      ) : (
                        <span>Add new position</span>
                      )}
                    </button>
                  )
                })}
              </div>

              {hasBlockedResult && (
                <p className="portfolio-limit-message">
                  Your Free portfolio is at its position limit.{' '}
                  <a href="/pricing">View upgrade options</a>
                </p>
              )}
            </div>
          )}

          {activePosition && (
            <>
              <div className="portfolio-selected-card">
                <div>
                  <strong>{activePosition.name}</strong>
                  <span>
                    {activePosition.set_name ?? 'Set unavailable'}
                    {'card_number' in activePosition && activePosition.card_number
                      ? ` / ${activePosition.card_number}`
                      : ''}
                  </span>
                </div>
                {mode === 'create' && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    disabled={busy}
                    onClick={() => {
                      setSelectedCard(null)
                      changeQuery('')
                      setFieldErrors({})
                    }}
                  >
                    Change card
                  </button>
                )}
              </div>

              <form className="portfolio-lot-form" onSubmit={submit} noValidate>
                <div className="portfolio-form-field">
                  <label htmlFor="portfolio-lot-quantity">Quantity</label>
                  <input
                    id="portfolio-lot-quantity"
                    inputMode="numeric"
                    value={quantity}
                    disabled={busy}
                    aria-invalid={Boolean(fieldErrors.quantity)}
                    aria-describedby={
                      fieldErrors.quantity ? 'portfolio-quantity-error' : undefined
                    }
                    onChange={event => setQuantity(event.target.value)}
                  />
                  {fieldErrors.quantity && (
                    <span id="portfolio-quantity-error" className="portfolio-field-error">
                      {fieldErrors.quantity}
                    </span>
                  )}
                </div>
                <div className="portfolio-form-field">
                  <label htmlFor="portfolio-lot-cost">Unit cost (USD)</label>
                  <input
                    id="portfolio-lot-cost"
                    inputMode="decimal"
                    value={unitCost}
                    disabled={busy}
                    aria-invalid={Boolean(fieldErrors.unitCost)}
                    aria-describedby={
                      fieldErrors.unitCost ? 'portfolio-cost-error' : undefined
                    }
                    onChange={event => setUnitCost(event.target.value)}
                  />
                  {fieldErrors.unitCost && (
                    <span id="portfolio-cost-error" className="portfolio-field-error">
                      {fieldErrors.unitCost}
                    </span>
                  )}
                </div>
                <div className="portfolio-form-field">
                  <label htmlFor="portfolio-lot-date">Purchase date</label>
                  <input
                    id="portfolio-lot-date"
                    type="date"
                    value={purchasedOn}
                    disabled={busy}
                    aria-invalid={Boolean(fieldErrors.purchasedOn)}
                    aria-describedby={
                      fieldErrors.purchasedOn ? 'portfolio-date-error' : undefined
                    }
                    onChange={event => setPurchasedOn(event.target.value)}
                  />
                  {fieldErrors.purchasedOn && (
                    <span id="portfolio-date-error" className="portfolio-field-error">
                      {fieldErrors.purchasedOn}
                    </span>
                  )}
                </div>

                <div className="portfolio-dialog-error" aria-live="polite">
                  {error && <span>{error}</span>}
                  {upgradeUrl && (
                    <a href={upgradeUrl}>View upgrade options</a>
                  )}
                </div>
                <footer className="portfolio-dialog-actions">
                  <button
                    type="button"
                    className="btn btn-ghost"
                    disabled={busy}
                    onClick={requestClose}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={busy}
                  >
                    {busy
                      ? mode === 'create' ? 'Adding lot' : 'Saving changes'
                      : mode === 'create' ? 'Add lot' : 'Save changes'}
                  </button>
                </footer>
              </form>
            </>
          )}
        </div>
      </div>
    </>
  )
}
