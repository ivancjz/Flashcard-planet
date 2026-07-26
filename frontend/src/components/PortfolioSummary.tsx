import type { PortfolioSummary as PortfolioSummaryType } from '../types/portfolio'

interface PortfolioSummaryProps {
  summary: PortfolioSummaryType
}

const usd = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
})

function money(value: string): string {
  return usd.format(Number(value))
}

export default function PortfolioSummary({ summary }: PortfolioSummaryProps) {
  const pnl = Number(summary.unrealized_pnl)
  const pnlState = pnl > 0 ? 'gain' : pnl < 0 ? 'loss' : 'flat'
  const pnlLabel = pnlState === 'gain'
    ? 'Gain'
    : pnlState === 'loss'
      ? 'Loss'
      : 'Flat'
  const pnlClass = pnlState === 'gain'
    ? 'portfolio-value-positive'
    : pnlState === 'loss'
      ? 'portfolio-value-negative'
      : ''
  const pnlAmount = pnl > 0
    ? `+${money(summary.unrealized_pnl)}`
    : money(summary.unrealized_pnl)

  return (
    <section className="portfolio-summary" aria-label="Portfolio summary">
      <div className="portfolio-summary-item">
        <span className="portfolio-summary-label">Total cost</span>
        <strong>{money(summary.total_cost_basis)}</strong>
        <span className="portfolio-summary-detail">
          {summary.position_count} {summary.position_count === 1 ? 'position' : 'positions'}
        </span>
      </div>
      <div className="portfolio-summary-item">
        <span className="portfolio-summary-label">Current value</span>
        <strong>{money(summary.total_market_value)}</strong>
        <span className="portfolio-summary-detail">Raw-priced positions</span>
      </div>
      <div className="portfolio-summary-item">
        <span className="portfolio-summary-label">Unrealized P&amp;L</span>
        <strong className={pnlClass}>{pnlAmount}</strong>
        <span className={`portfolio-summary-detail ${pnlClass}`}>
          <span>{pnlLabel}</span>
          {summary.unrealized_pnl_percent === null
            ? ''
            : ` (${Number(summary.unrealized_pnl_percent).toFixed(2)}%)`}
        </span>
      </div>
      <div className="portfolio-summary-item">
        <span className="portfolio-summary-label">Valuation coverage</span>
        <strong>{Number(summary.valuation_coverage_percent).toFixed(2)}%</strong>
        <span className="portfolio-summary-detail">
          {summary.priced_position_count} of {summary.position_count} priced
        </span>
      </div>
    </section>
  )
}
