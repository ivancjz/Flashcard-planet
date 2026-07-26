import { useCallback, useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import { useFocusTrap } from '../hooks/useFocusTrap'
import { useScrollLock } from '../hooks/useScrollLock'
import type { PortfolioLot, PortfolioPosition } from '../types/portfolio'

interface PortfolioDeleteDialogProps {
  open: boolean
  position: PortfolioPosition | null
  lot: PortfolioLot | null
  busy: boolean
  onClose: () => void
  onConfirm: (lotId: string) => Promise<void>
}

const usd = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
})

function dateLabel(value: string): string {
  const parsed = new Date(`${value}T00:00:00Z`)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(parsed)
}

export default function PortfolioDeleteDialog({
  open,
  position,
  lot,
  busy,
  onClose,
  onConfirm,
}: PortfolioDeleteDialogProps) {
  const busyRef = useRef(busy)
  const onCloseRef = useRef(onClose)

  useEffect(() => {
    busyRef.current = busy
    onCloseRef.current = onClose
  }, [busy, onClose])

  const requestClose = useCallback(() => {
    if (!busyRef.current) onCloseRef.current()
  }, [])
  const trapRef = useFocusTrap<HTMLDivElement>(open, requestClose)
  useScrollLock(open)

  if (!open || !position || !lot) return null

  return (
    <>
      <div
        className="modal-backdrop portfolio-dialog-backdrop"
        data-testid="portfolio-delete-backdrop"
        aria-hidden="true"
        onMouseDown={requestClose}
      />
      <div
        ref={trapRef}
        className="modal portfolio-dialog portfolio-delete-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="portfolio-delete-title"
        aria-busy={busy || undefined}
      >
        <header className="portfolio-dialog-header">
          <div>
            <span className="portfolio-dialog-eyebrow">Portfolio</span>
            <h2 id="portfolio-delete-title">Delete purchase lot</h2>
          </div>
          <button
            type="button"
            className="icon-button portfolio-dialog-close"
            aria-label="Close delete dialog"
            title="Close delete dialog"
            disabled={busy}
            onClick={requestClose}
          >
            <X size={18} aria-hidden="true" />
          </button>
        </header>
        <div className="portfolio-dialog-body">
          <p>This removes the purchase record from your portfolio.</p>
          <div className="portfolio-delete-summary">
            <strong>{position.name}</strong>
            <time dateTime={lot.purchased_on}>{dateLabel(lot.purchased_on)}</time>
            <span>Quantity: {lot.quantity}</span>
            <span>Unit cost: {usd.format(Number(lot.unit_cost_usd))}</span>
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
              type="button"
              className="btn portfolio-delete-confirm"
              disabled={busy}
              onClick={() => {
                void onConfirm(lot.id)
              }}
            >
              {busy ? 'Deleting lot' : 'Delete lot'}
            </button>
          </footer>
        </div>
      </div>
    </>
  )
}
