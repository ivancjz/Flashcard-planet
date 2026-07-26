import { Fragment, useState } from 'react'
import {
  ChevronDown,
  ChevronRight,
  Pencil,
  Trash2,
} from 'lucide-react'
import type { PortfolioLot, PortfolioPosition } from '../types/portfolio'

interface PortfolioPositionTableProps {
  positions: PortfolioPosition[]
  onEditLot: (position: PortfolioPosition, lot: PortfolioLot) => void
  onDeleteLot: (position: PortfolioPosition, lot: PortfolioLot) => void
}

const usd = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
})

function money(value: string): string {
  return usd.format(Number(value))
}

function signedMoney(value: string): string {
  const numeric = Number(value)
  return numeric > 0 ? `+${money(value)}` : money(value)
}

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

function gameLabel(value: string): string {
  return value
    .split('_')
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(' ')
}

function orderedLots(lots: PortfolioLot[]): PortfolioLot[] {
  return [...lots].sort((left, right) => (
    right.purchased_on.localeCompare(left.purchased_on)
    || right.created_at.localeCompare(left.created_at)
    || left.id.localeCompare(right.id)
  ))
}

export default function PortfolioPositionTable({
  positions,
  onEditLot,
  onDeleteLot,
}: PortfolioPositionTableProps) {
  const [expandedAssets, setExpandedAssets] = useState<Set<string>>(
    () => new Set(),
  )

  function togglePosition(assetId: string) {
    setExpandedAssets(current => {
      const next = new Set(current)
      if (next.has(assetId)) {
        next.delete(assetId)
      } else {
        next.add(assetId)
      }
      return next
    })
  }

  if (positions.length === 0) {
    return (
      <section className="portfolio-positions" aria-labelledby="portfolio-positions-title">
        <div className="portfolio-section-heading">
          <h2 id="portfolio-positions-title">Positions</h2>
        </div>
        <p className="portfolio-positions-empty">
          No purchase lots have been added yet.
        </p>
      </section>
    )
  }

  return (
    <section className="portfolio-positions" aria-labelledby="portfolio-positions-title">
      <div className="portfolio-section-heading">
        <h2 id="portfolio-positions-title">Positions</h2>
        <span>{positions.length} grouped holdings</span>
      </div>
      <div className="portfolio-table-wrap">
        <table className="portfolio-table">
          <thead>
            <tr>
              <th scope="col">Card</th>
              <th scope="col">Qty</th>
              <th scope="col">Avg cost</th>
              <th scope="col">Cost basis</th>
              <th scope="col">Raw price</th>
              <th scope="col">Current value</th>
              <th scope="col">Unrealized P&amp;L</th>
            </tr>
          </thead>
          <tbody>
            {positions.map(position => {
              const expanded = expandedAssets.has(position.asset_id)
              const disclosureLabel = `${
                expanded ? 'Collapse' : 'Expand'
              } lots for ${position.name}`
              const lotRegionId = `portfolio-lots-${position.asset_id}`
              const pnl = position.unrealized_pnl_usd === null
                ? null
                : Number(position.unrealized_pnl_usd)
              const pnlClass = pnl === null || pnl === 0
                ? ''
                : pnl > 0
                  ? 'portfolio-value-positive'
                  : 'portfolio-value-negative'

              return (
                <Fragment key={position.asset_id}>
                  <tr className="portfolio-position-row">
                    <td>
                      <div className="portfolio-position-identity">
                        <button
                          type="button"
                          className="icon-button portfolio-disclosure"
                          aria-expanded={expanded}
                          aria-controls={lotRegionId}
                          aria-label={disclosureLabel}
                          title={disclosureLabel}
                          onClick={() => togglePosition(position.asset_id)}
                        >
                          {expanded
                            ? <ChevronDown size={16} aria-hidden="true" />
                            : <ChevronRight size={16} aria-hidden="true" />}
                        </button>
                        <div>
                          <strong>{position.name}</strong>
                          <span>
                            {position.set_name ?? gameLabel(position.game)}
                            {position.card_number ? ` / ${position.card_number}` : ''}
                          </span>
                        </div>
                      </div>
                    </td>
                    <td>{position.quantity}</td>
                    <td>{money(position.average_unit_cost_usd)}</td>
                    <td>{money(position.cost_basis_usd)}</td>
                    <td>
                      {position.latest_raw_price_usd === null
                        ? '-'
                        : money(position.latest_raw_price_usd)}
                    </td>
                    <td>
                      {position.market_value_usd === null
                        ? <span className="portfolio-unpriced">Unpriced</span>
                        : money(position.market_value_usd)}
                    </td>
                    <td className={pnlClass}>
                      {position.unrealized_pnl_usd === null
                        ? '-'
                        : (
                            <>
                              {signedMoney(position.unrealized_pnl_usd)}
                              <span className="portfolio-pnl-label">
                                {pnl !== null && pnl > 0
                                  ? 'Gain'
                                  : pnl !== null && pnl < 0
                                    ? 'Loss'
                                    : 'Flat'}
                              </span>
                            </>
                          )}
                    </td>
                  </tr>
                  {expanded && (
                    <tr className="portfolio-lots-row" id={lotRegionId}>
                      <td colSpan={7}>
                        <table
                          className="portfolio-lots-table"
                          aria-label={`Purchase lots for ${position.name}`}
                        >
                          <thead>
                            <tr>
                              <th scope="col">Purchased</th>
                              <th scope="col">Quantity</th>
                              <th scope="col">Unit cost</th>
                              <th scope="col">Lot cost</th>
                              <th scope="col">Actions</th>
                            </tr>
                          </thead>
                          <tbody>
                            {orderedLots(position.lots).map(lot => {
                              const purchased = dateLabel(lot.purchased_on)
                              return (
                                <tr key={lot.id}>
                                  <td>{purchased}</td>
                                  <td>{lot.quantity}</td>
                                  <td>{money(lot.unit_cost_usd)}</td>
                                  <td>
                                    {usd.format(
                                      lot.quantity * Number(lot.unit_cost_usd),
                                    )}
                                  </td>
                                  <td>
                                    <div className="portfolio-lot-actions">
                                      <button
                                        type="button"
                                        className="icon-button"
                                        aria-label={`Edit lot purchased ${purchased}`}
                                        title={`Edit lot purchased ${purchased}`}
                                        onClick={() => onEditLot(position, lot)}
                                      >
                                        <Pencil size={15} aria-hidden="true" />
                                      </button>
                                      <button
                                        type="button"
                                        className="icon-button portfolio-delete-button"
                                        aria-label={`Delete lot purchased ${purchased}`}
                                        title={`Delete lot purchased ${purchased}`}
                                        onClick={() => onDeleteLot(position, lot)}
                                      >
                                        <Trash2 size={15} aria-hidden="true" />
                                      </button>
                                    </div>
                                  </td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
